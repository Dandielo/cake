"""The Gcc Compiler.
"""

import os
import os.path
import re
import subprocess
import tempfile

import cake.filesys
import cake.path
from cake.library import memoise
from cake.library.compilers import Compiler, makeCommand

def _escapeArg(arg):
  if ' ' in arg:
    if '"' in arg:
      arg = arg.replace('"', '\\"')
    return '"%s"' % arg
  else:
    return arg
  
class GccCompiler(Compiler):

# TODO: Is this needed?
  name = 'gcc'

  _lineRegex = re.compile('# [0-9]+ "(?!\<)(?P<path>.+)"', re.MULTILINE)
  
  useSse = False
  
  def __init__(
    self,
    ccExe=None,
    arExe=None,
    ldExe=None,
    architecture=None,
    ):
    Compiler.__init__(self)
    self.__ccExe = ccExe
    self.__arExe = arExe
    self.__ldExe = ldExe
    self.__architecture = architecture
    
    if architecture == 'x86':
      self.moduleSuffix = '.dll'
      self.programSuffix = '.exe' 

# TODO: Is this needed?
  @property
  def architecture(self):
    return self.__architecture
  
  @memoise
  def _getProcessEnv(self):
    temp = os.environ.get('TMP', os.environ.get('TEMP', os.getcwd()))
    env = {
      'COMPSPEC' : os.environ.get('COMSPEC', ''),
      'PATHEXT' : ".com;.exe;.bat;.cmd",
      'SYSTEMROOT' : os.environ.get('SYSTEMROOT', ''),
      'TMP' : temp,
      'TEMP' : temp,  
      'PATH' : '.',
      }
    if env['SYSTEMROOT']:
      env['PATH'] = os.path.pathsep.join([
        env['PATH'],
        os.path.join(env['SYSTEMROOT'], 'System32'),
        env['SYSTEMROOT'],
        ])
    return env

  def _executeProcess(
    self,
    args,
    target,
    engine,
    wantStdout=False
    ):
# TODO: Why does Lewis use a response file for some things but not others?
    engine.logger.outputDebug(
      "run",
      "run: %s\n" % " ".join(args),
      )
      
    cake.filesys.makeDirs(cake.path.dirName(target))
    
# TODO: Response file support...but gcc 3.x doesn't support it???     
#    argsFile = target + '.args'
#    with open(argsFile, 'wt') as f:
#      for arg in args[1:]:
#        f.write(arg + '\n')
      
    with tempfile.TemporaryFile() as errFile:
      try:
        p = subprocess.Popen(
          #args=[args[0], '@' + argsFile],
          args=args,
          executable=args[0],
          env=self._getProcessEnv(),
          stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,
          stderr=errFile,
          )
      except EnvironmentError, e:
        engine.raiseError(
          "cake: failed to launch %s: %s\n" % (args[0], str(e))
          )
    
      p.stdin.close()
      output = p.stdout.read()
      exitCode = p.wait()
  
      errFile.seek(0)
      errString = errFile.read()
  
    if not wantStdout:
      errString += output
      
    if errString:
      engine.logger.outputWarning(errString + '\n')
        
    if exitCode != 0:
      engine.raiseError("%s: failed with exit code %i\n" % (args[0], exitCode))
    
    return output
  
  @memoise
  def _getCommonArgs(self, language):
    args = [self.__ccExe]

    # Almost all compile options can also set preprocessor defines (see
    # http://gcc.gnu.org/onlinedocs/cpp/Common-Predefined-Macros.html),
    # so for safety all compile options are shared across preprocessing
    # for compiling.
    # To dump predefined compiler macros: 'echo | gcc -E -dM -'
    args.extend(['-x', language])

    if self.debugSymbols:
      args.append('-g')

    if language == 'c++':
      if self.enableRtti:
        args.append('-frtti')
      else:
        args.append('-fno-rtti')

    if self.enableExceptions:
      args.append('-fexceptions')
    else:
      args.append('-fno-exceptions')
      
    if self.optimisation == self.NO_OPTIMISATION:
      args.append('-O0')
    elif self.optimisation == self.PARTIAL_OPTIMISATION:
      args.append('-O2')
    elif self.optimisation == self.FULL_OPTIMISATION:
      args.append('-O4')

    if self.useSse:
      args.append('-msse')
    
    return args

  @memoise
  def _getCompileArgs(self, language):
    args = list(self._getCommonArgs(language))
    
    args.append('-c')

    return args

  @memoise
  def _getPreprocessArgs(self, language):
    args = list(self._getCommonArgs(language))

    args.append('-E')
    
    for p in reversed(self.includePaths):
      args.extend(['-I', p])

    args.extend('-D' + d for d in self.defines)
    
# TODO: Should Lewis reverse this in msvc.py?    
    for p in reversed(self.forceIncludes):
      args.extend(['-include', p])

    return args
    
  def getObjectCommands(self, target, source, engine):
    
    language = self.language
    if not language:
      if source.lower().endswith('.c'):
        language = 'c'
      else:
        language = 'c++'
    
    preprocessTarget = target + '.ii'

    preprocessArgs = list(self._getPreprocessArgs(language))
# TODO: Check speed of writing to disk vs stdout    
    preprocessArgs += [source]#, '-o', preprocessTarget]
    
    compileArgs = list(self._getCompileArgs(language))
    compileArgs += [preprocessTarget, '-o', target]
    
    preprocessorOutput = []
 
# TODO: Why is this command different? 
    @makeCommand(preprocessArgs + ['>', _escapeArg(preprocessTarget)])
    def preprocess():
      output = self._executeProcess(
        preprocessArgs,
        preprocessTarget,
        engine,
        True
        )
      with open(preprocessTarget, 'wb') as f:
        f.write(output)

      preprocessorOutput.append(output)

    @makeCommand("gcc-scan")
    def scan():
      engine.logger.outputDebug(
        "scan",
        "scan: %s\n" % preprocessTarget,
        )
      # TODO: Add dependencies on DLLs used by cc.exe
      dependencies = [self.__ccExe]
      uniqueDeps = set()
# TODO: Check speed of line at a time vs whole file      
      for match in self._lineRegex.finditer(preprocessorOutput[0]):
        path = match.group('path').replace('\\\\', '\\')
        if path not in uniqueDeps:
          uniqueDeps.add(path)
          if not cake.filesys.isFile(path):
            engine.logger.outputDebug(
              "scan",
              "scan: Ignoring missing include '" + path + "'\n",
              )
          else:
            dependencies.append(path)
      return dependencies

    @makeCommand(compileArgs)
    def compile():
      self._executeProcess(compileArgs, target, engine)

    canBeCached = True
    return preprocess, scan, compile, canBeCached    

  @memoise
  def _getCommonLibraryArgs(self):
    args = [self.__arExe]
    
    # r - Replace existing/insert new files
    # P - Use full path names when matching
    # c - Don't warn if we had to create new file
    # s - Build an index
    # u - Update files that are newer
    # v - Be verbose
    args.append('-rcPs')

    return args

  def getLibraryCommand(self, target, sources, engine):

    args = list(self._getCommonLibraryArgs())
    args.append(target)
    args.extend(sources)
    
    @makeCommand(args)
    def archive():

      # Remove the target so the object order and deleted objs update properly
      cake.filesys.remove(target)
      self._executeProcess(args, target, engine)

    @makeCommand("lib-scan")
    def scan():
      # TODO: Add dependencies on DLLs used by lib.exe
      return [self.__arExe] + sources

    return archive, scan

  @memoise
  def _getCommonLinkArgs(self, dll):
    
    args = [self.__ldExe]

    if dll:
      args.append('-shared')

    return args
  
  def getProgramCommands(self, target, sources, engine):
    return self._getLinkCommands(target, sources, engine, dll=False)
  
  def getModuleCommands(self, target, sources, engine):
    return self._getLinkCommands(target, sources, engine, dll=True)

  def _getLinkCommands(self, target, sources, engine, dll):
    
# TODO: Library paths returns absolute paths to libraries,
#  so why do we add paths as well???
# TODO: We should reverse libraries as well as library paths
    libraries = self._resolveLibraries(engine)
    sources += libraries    
    #sources += ['-l' + l for l in libraries]    
    
    args = list(self._getCommonLinkArgs(dll))
    #args.extend('-L' + p for p in self.libraryPaths)
    args.extend(sources)
    args.extend(['-o', target])
    
    @makeCommand(args)
    def link():
      self._executeProcess(args, target, engine)      
    
    @makeCommand("link-scan")
    def scan():
      # TODO: Add dependencies on DLLs used by link.exe
      return [self.__ldExe] + sources
    
    return link, scan
