"""Base Class and Utilities for C/C++ Compiler Tools.

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

__all__ = ["Compiler"]

import weakref
import os.path
import binascii
try:
  import cPickle as pickle
except ImportError:
  import pickle

import cake.path
import cake.filesys
import cake.hash
from cake.engine import Script, DependencyInfo, FileInfo, BuildError
from cake.library import (
  Tool, FileTarget, getPathsAndTasks, getPathAndTask, memoise
  )
from cake.task import Task

class CompilerNotFoundError(Exception):
  pass

class PchTarget(FileTarget):
  def __init__(self, path, header, object, task):
    self.path = path
    self.header = header
    self.object = object
    self.task = task

def getLinkPathsAndTasks(files):
  paths = []
  tasks = []
  for f in files:
    if isinstance(f, PchTarget):
      if f.object is not None:
        paths.append(f.object)
        tasks.append(f.task)
    elif isinstance(f, FileTarget):
      paths.append(f.path)
      tasks.append(f.task)
    else:
      paths.append(f)
  return paths, tasks

class Command(object):
  
  def __init__(self, args, func):
    self.args = args
    self.func = func
    
  def __repr__(self):
    return repr(self.args)
  
  def __call__(self, *args):
    return self.func(*args)

def makeCommand(args):
  def run(func):
    return Command(args, func)
  return run
      
class Compiler(Tool):
  """Base class for C/C++ compiler tools.
  
  @ivar debugSymbols: If true then the compiler will output debug symbols.
  @type debugSymbols: boolean
  """
  
  NO_OPTIMISATION = 0
  PARTIAL_OPTIMISATION = 1
  FULL_OPTIMISATION = 2

  # Map of engine to map of library path to list of object paths
  __libraryObjects = weakref.WeakKeyDictionary()

  ###
  # Default settings
  ###
  
  debugSymbols = False
  optimisation = NO_OPTIMISATION
  
  enableRtti = True
  enableExceptions = True
  
  warningLevel = None
  warningsAsErrors = False
  
  objectSuffix = '.o'
  libraryPrefixSuffixes = [('lib', '.a')]
  moduleSuffix = '.so'
  programSuffix = ''
  pchSuffix = '.gch'
  
  linkObjectsInLibrary = False
  outputMapFile = False
  useIncrementalLinking = False
  useFunctionLevelLinking = False
  stackSize = None
  heapSize = None

  linkerScript = None
    
  objectCachePath = None
  
  # Set this if the object cache is to be shared across workspaces.
  # This will cause objects and their dependencies under this directory
  # to be stored as paths relative to this directory. This allows 
  # workspaces at different paths to reuse object files with the 
  # potential danger of debug information embedded in the object
  # files referring to paths in the wrong workspace.
  objectCacheWorkspaceRoot = None

  language = None
 
  # This is defined here so that .cake scripts don't have to
  # check if the compiler is msvc before setting it. Compilers
  # that don't use them can just ignore them. 
  pdbFile = None
  strippedPdbFile = None
  subSystem = None
  importLibrary = None
  embedManifest = False
  useSse = False
  
  def __init__(self):
    super(Compiler, self).__init__()
    self.cFlags = []
    self.cppFlags = []
    self.mFlags = []
    self.moduleFlags = []
    self.programFlags = []
    self.includePaths = []
    self.defines = []
    self.forcedIncludes = []
    self.libraryScripts = []
    self.libraryPaths = []
    self.libraries = []
    self.moduleScripts = []
    self.modules = []

  @classmethod
  def _getObjectsInLibrary(cls, engine, path):
    """Get a list of the paths of object files in the specified library.
    
    @param engine: The Engine that is looking up the results.
    @type engine: cake.engine.Engine
    
    @param path: Path of the library previously built by a call to library().
    
    @return: A tuple of the paths of objects in the library.
    """
    path = os.path.normcase(os.path.normpath(path))
    libraryObjects = cls.__libraryObjects.get(engine, None)
    if libraryObjects:
      return libraryObjects.get(path, None)
    else:
      return None

  @classmethod
  def _setObjectsInLibrary(cls, engine, path, objectPaths):
    """Set the list of paths of object files in the specified library.
    
    @param engine: The Engine that is looking up the results.
    @type engine: cake.engine.Engine
    
    @param path: Path of the library previously built by a call to library().
    @type path: string
    
    @param objectPaths: A list of the objects built by a call to library().
    @type objectPaths: list of strings
    """
    path = os.path.normcase(os.path.normpath(path))
    libraryObjects = cls.__libraryObjects.setdefault(engine, {})
    libraryObjects[path] = tuple(objectPaths)

  def addCFlag(self, flag):
    """Add a flag to be used during .c compilation.
    
    @param flag: The flag to add.
    @type flag: string
    """
    self.cFlags.append(flag)
    self._clearCache()
    
  def addCFlags(self, flags):
    """Add a list of flags to be used during .c compilation.

    @param flags: The flags to add.
    @type flags: list of string
    """
    self.cFlags.extend(flags)
    self._clearCache()

  def addCppFlag(self, flag):
    """Add a flag to be used during .cpp compilation.
    
    @param flag: The flag to add.
    @type flag: string
    """
    self.cppFlags.append(flag)
    self._clearCache()
    
  def addCppFlags(self, flags):
    """Add a list of flags to be used during .cpp compilation.

    @param flags: The flags to add.
    @type flags: list of string
    """
    self.cppFlags.extend(flags)
    self._clearCache()

  def addMFlag(self, flag):
    """Add a flag to be used during Objective C compilation.
    
    @param flag: The flag to add.
    @type flag: string
    """
    self.mFlags.append(flag)
    self._clearCache()
    
  def addMFlags(self, flags):
    """Add a list of flags to be used during Objective C compilation.

    @param flags: The flags to add.
    @type flags: list of string
    """
    self.mFlags.extend(flags)
    self._clearCache()

  def addModuleFlag(self, flag):
    """Add a flag to be used during linking of modules.
    
    @param flag: The flag to add.
    @type flag: string
    """
    self.moduleFlags.append(flag)
    self._clearCache()
    
  def addModuleFlags(self, flags):
    """Add a list of flags to be used during linking of modules.

    @param flags: The flags to add.
    @type flags: list of string
    """
    self.moduleFlags.extend(flags)
    self._clearCache()

  def addProgramFlag(self, flag):
    """Add a flag to be used during linking of programs.

    @param flag: The flag to add.
    @type flag: string
    """
    self.programFlags.append(flag)
    self._clearCache()
    
  def addProgramFlags(self, flags):
    """Add a list of flags to be used during linking of programs.

    @param flags: The flags to add.
    @type flags: list of string
    """
    self.programFlags.extend(flags)
    self._clearCache()

  def addIncludePath(self, path):
    """Add an include path to the preprocessor search path.
    
    The newly added path will have search precedence over any
    existing paths.
    
    @param path: The path to add.
    @type path: string
    """
    self.includePaths.append(path)
    self._clearCache()
    
  def addDefine(self, name, value=None):
    """Add a define to the preprocessor command-line.

    The newly added define will have precedence over any
    existing defines with the same name.
    
    @param name: The name of the define to set.
    @type name: string
    @param value: An optional value for the define.
    @type value: string or None
    """
    if value is None:
      self.defines.append(name)
    else:
      self.defines.append("{0}={1}".format(name, value))
    self._clearCache()

  def addForcedInclude(self, path):
    """Add a file to be forcibly included on the command-line.

    The newly added forced include will be included after any
    previous forced includes.

    @param path: The path to the forced include file. This may need
    to be relative to a previously defined includePath. 
    @type path: string
    """
    self.forcedIncludes.append(path)
    self._clearCache()

  def addLibrary(self, name):
    """Add a library to the list of libraries to link with.
    
    The newly added library will have search precedence over any
    existing libraries.

    @param name: Name/path of the library to link with.
    @type name: string
    """
    self.libraries.append(name)
    self._clearCache()

  def addLibraryPath(self, path):
    """Add a path to the list of library search paths.
    
    The newly added path will have search precedence over any
    existing paths.
    
    @param path: The path to add.
    @type path: string
    """
    self.libraryPaths.append(path)
    self._clearCache()
    
  def addLibraryScript(self, path):
    """Add a script to be executed before performing a link.
    
    The script will be executed prior to any subsequent
    program() or module() targets being built.
    
    @param path: Path of the script to execute.
    @type path: string
    """
    self.libraryScripts.append(path)
    self._clearCache()

  def addModule(self, name):
    """Add a module to the list of modules to copy.
    
    @param name: Name/path of the module to copy.
    @type name: string
    """
    self.modules.append(name)
    self._clearCache()
    
  def addModuleScript(self, path):
    """Add a script to be executed before copying modules.
    
    The script will be executed by the copyModulesTo()
    function.
    
    @param path: Path of the script to execute.
    @type path: string
    """
    self.moduleScripts.append(path)
    self._clearCache()
    
  def copyModulesTo(self, targetDir, **kwargs):
    """Copy modules to the given target directory.
    
    The modules copied are those previously specified by the
    addModule() function.
    
    @param targetDir: The directory to copy modules to.
    @type targetDir: string

    @return: A list of Task objects, one for each module being
    copied.
    @rtype: list of L{Task}
    """
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)

    script = Script.getCurrent()
    engine = Script.getCurrent().engine

    tasks = []
    for moduleScript in compiler.moduleScripts:
      tasks.append(engine.execute(moduleScript, script.variant))

    def doCopy(source, targetDir):
      # Try without and with the extension
      if not cake.filesys.isFile(source):
        source = cake.path.forceExtension(source, compiler.moduleSuffix)
      target = cake.path.join(targetDir, cake.path.baseName(source))
      
      if engine.forceBuild:
        reasonToBuild = "rebuild has been forced"
      elif not cake.filesys.isFile(target):
        reasonToBuild = "'%s' does not exist" % target
      elif engine.getTimestamp(source) > engine.getTimestamp(target):
        reasonToBuild = "'%s' is newer than '%s'" % (source, target)
      else:
        # up-to-date
        return

      engine.logger.outputDebug(
        "reason",
        "Rebuilding '%s' because %s.\n" % (target, reasonToBuild),
        )
      engine.logger.outputInfo("Copying %s to %s\n" % (source, target))
      
      try:
        cake.filesys.makeDirs(targetDir)
        cake.filesys.copyFile(source, target)
      except EnvironmentError, e:
        engine.raiseError("%s: %s\n" % (target, str(e)))

      engine.notifyFileChanged(target)

    moduleTasks = []
    for module in compiler.modules:
      copyTask = engine.createTask(
        lambda s=module,t=targetDir:
          doCopy(s, t)
        )
      copyTask.startAfter(tasks)
      moduleTasks.append(copyTask)
    
    return moduleTasks

  def pch(self, target, source, header, forceExtension=True, **kwargs):
    """Compile an individual header to a pch file.
    
    @param target: Path to the target pch file.
    @type target: string
    
    @param header: Path to the header as it would be included
    by other source files.
    @type header: string.
    
    @param forceExtension: If true then the target path will have
    the default pch file extension appended if it doesn't already
    have it.
    @type forceExtension: bool
    
    @return: A PchTarget containing the path of the pch file
    that will be built and the task that will build it.
    @rtype: L{PchTarget}
    """
     
    # Take a snapshot of the build settings at this point and use that.
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)
      
    return compiler._pch(target, source, header, forceExtension)

  def _pch(self, target, source, header, forceExtension=True):
    
    # Make note of which build engine we're using too
    engine = Script.getCurrent().engine

    if forceExtension:
      target = cake.path.forceExtension(target, self.pchSuffix)
    object = self._getPchObject(target)
    
    source, sourceTask = getPathAndTask(source)
    
    pchTask = engine.createTask(
      lambda t=target, s=source, h=header, o=object, e=engine, c=self:
        c.buildPch(t, s, h, o, e)
      )
    pchTask.startAfter(sourceTask)
    
    return PchTarget(path=target, header=header, object=object, task=pchTask)
    
  def _getPchObject(self, path):
    """Return the path to the pch object file given a pch target path.
    
    @param path: Path to the target pch file.
    @type path: string
    
    @return: Path to the pch object file or None if not supported by this
    compiler.
    @rtype: string or None
    """
    return None

  def object(self, target, source, pch=None, forceExtension=True, **kwargs):
    """Compile an individual source to an object file.
    
    @param target: Path of the target object file.
    @type target: string
    
    @param source: Path of the source file.
    @type source: string or FileTarget.
    
    @param pch: A precompiled header file to use. This file can be built
    with the pch() function.
    @type pch: L{PchTarget}
    
    @param forceExtension: If true then the target path will have
    the default object file extension appended if it doesn't already
    have it.
    @type forceExtension: bool
    
    @return: A FileTarget containing the path of the object file
    that will be built and the task that will build it.
    @rtype: L{FileTarget}
    """
     
    # Take a snapshot of the build settings at this point and use that.
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)
      
    return compiler._object(target, source, pch, forceExtension)
    
  def _object(self, target, source, pch=None, forceExtension=True):
    
    # Make note of which build engine we're using too
    engine = Script.getCurrent().engine
    
    if forceExtension:
      target = cake.path.forceExtension(target, self.objectSuffix)
    
    prerequisiteTasks = list(self._getObjectPrerequisiteTasks())
    
    source, sourceTask = getPathAndTask(source)
    if sourceTask is not None:      prerequisiteTasks.append(sourceTask)
    
    _, pchTask = getPathAndTask(pch)
    if pchTask is not None:
      prerequisiteTasks.append(pchTask)
    
    objectTask = engine.createTask(
      lambda t=target, s=source, p=pch, e=engine, c=self:
        c.buildObject(t, s, p, e)
      )
    objectTask.startAfter(prerequisiteTasks)
    
    return FileTarget(path=target, task=objectTask)
    
  @memoise
  def _getObjectPrerequisiteTasks(self):
    """Return a list of the tasks that are prerequisites for
    building an object file.
    """
    return getPathsAndTasks(self.forcedIncludes)[1]
    
  def objects(self, targetDir, sources, pch, **kwargs):
    """Build a collection of objects to a target directory.
    
    @param targetDir: Path to the target directory where the built objects
    will be placed.
    @type targetDir: string
    
    @param sources: A list of source files to compile to object files.
    @type sources: sequence of string or FileTarget objects
    
    @param pch: A precompiled header file to use. This file can be built
    with the pch() function.
    @type pch: L{PchTarget}
    
    @return: A list of FileTarget objects, one for each object being
    built.
    """
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)
    
    results = []
    for source in sources:
      sourcePath, _ = getPathAndTask(source)
      sourceName = cake.path.baseNameWithoutExtension(sourcePath)
      targetPath = cake.path.join(targetDir, sourceName)
      results.append(compiler._object(
        targetPath,
        source,
        pch=pch,
        ))
    return results
    
  def library(self, target, sources, forceExtension=True, **kwargs):
    """Build a library from a collection of objects.
    
    @param target: Path of the library file to build.
    @type target: string
    
    @param sources: A list of object files to archive.
    @type sources: list of string or FileTarget
    
    @param forceExtension: If True then the target path will have
    the default library extension appended to it if it not already
    present.
    
    @return: A FileTarget object representing the library that will
    be built and the task that will build it.
    """

    # Take a snapshot of the current compiler settings
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)
  
    # And a copy of the current build engine
    engine = Script.getCurrent().engine

    paths, tasks = getPathsAndTasks(sources)
    
    if forceExtension:
      prefix, suffix = self.libraryPrefixSuffixes[0]
      target = cake.path.forcePrefixSuffix(target, prefix, suffix)
    
    self._setObjectsInLibrary(engine, target, paths)
    
    libraryTask = engine.createTask(
      lambda t=target, s=paths, e=engine, c=compiler:
        c.buildLibrary(t, s, e)
      )
    libraryTask.startAfter(tasks)
    
    return FileTarget(path=target, task=libraryTask)
    
  def module(self, target, sources, forceExtension=True, **kwargs):
    """Build a module/dynamic-library.
    
    Modules are executable code that can be dynamically loaded at
    runtime. On some platforms they are referred to as shared-libraries
    or dynamically-linked-libraries (DLLs).
    """
    
    # Take a snapshot of the current compiler settings
    compiler = self.clone()
    for k, v in kwargs.iteritems():
      setattr(compiler, k, v)
  
    # And a copy of the current build engine
    script = Script.getCurrent()
    engine = script.engine

    paths, tasks = getLinkPathsAndTasks(sources)

    for libraryScript in compiler.libraryScripts:
      tasks.append(engine.execute(libraryScript, script.variant))
    
    if forceExtension:
      target = cake.path.forceExtension(target, compiler.moduleSuffix)
      if compiler.importLibrary:
        prefix, suffix = self.libraryPrefixSuffixes[0]
        compiler.importLibrary = cake.path.forcePrefixSuffix(
          compiler.importLibrary,
          prefix,
          suffix,
          )
    
    moduleTask = engine.createTask(
      lambda t=target, s=paths, e=engine, c=compiler:
        c.buildModule(t, s, e)
      )
    moduleTask.startAfter(tasks)
    
    # XXX: What about returning paths to import libraries?
    
    return FileTarget(path=target, task=moduleTask)

  def program(self, target, sources, forceExtension=True, **kwargs):
    """Build an executable program.

    @param target: Path to the target executable.
    @type target: string
    
    @param sources: A list of source objects/libraries to be linked
    into the executable.
    @type sources: sequence of string/FileTarget
    
    @param forceExtension: If True then target path will have the
    default executable extension appended if it doesn't already have
    it.
    """
    
    # Take a snapshot of the current compiler settings
    compiler = self.clone()
    for name, value in kwargs.iteritems():
      setattr(compiler, name, value)
  
    # And a copy of the current build engine
    script = Script.getCurrent()
    engine = script.engine

    paths, tasks = getLinkPathsAndTasks(sources)
    
    for libraryScript in compiler.libraryScripts:
      tasks.append(engine.execute(libraryScript, script.variant))
    
    if forceExtension:
      target = cake.path.forceExtension(target, compiler.programSuffix)
    
    programTask = engine.createTask(
      lambda t=target, s=paths, e=engine, c=compiler:
        c.buildProgram(t, s, e)
      )
    programTask.startAfter(tasks)
    
    return FileTarget(path=target, task=programTask)
        
  ###########################
  # Internal methods not part of public API
  
  def _resolveLibraries(self, engine):
    """Resolve the list of library names to library paths.
    
    Searches for each library in the libraryPaths.
    If self.linkObjectsInLibrary is True then returns the paths of object files
    that comprise the library instead of the library path.
    
    @param engine: The engine to use for logging error messages.
    @type engine: cake.engine.Engine
    
    @return: A tuple containing a list of paths to resolved
    libraries/objects, followed by a list of unresolved libraries.
    @rtype: tuple of (list of string, list of string)
    """
    libraryPaths = []
    unresolvedLibs = []
    for library in reversed(self.libraries):
      fileNames = [library]

      libraryExtension = os.path.normcase(cake.path.extension(library))
      for prefix, suffix in self.libraryPrefixSuffixes:
        if libraryExtension != os.path.normcase(suffix):
          fileNames.append(cake.path.addPrefix(library, prefix) + suffix)

      # Add [""] so we search for the full path first 
      for candidate in cake.path.join(reversed(self.libraryPaths + [""]), fileNames):
        if cake.filesys.isFile(candidate):
          libraryPaths.append(candidate)
          break
      else:
        engine.logger.outputDebug(
          "scan",
          "scan: Ignoring missing library '" + library + "'\n",
          )
        unresolvedLibs.append(library)
      
    if self.linkObjectsInLibrary:
      results = []
      for libraryPath in libraryPaths:
        objects = self._getObjectsInLibrary(engine, libraryPath)
        if objects is None:
          results.append(libraryPath)
        else:
          results.extend(objects)
      return results, unresolvedLibs
    else:
      return libraryPaths, unresolvedLibs
  
  def buildPch(self, target, source, header, object, engine):
    compile, args, _ = self.getPchCommands(
      target,
      source,
      header,
      object,
      engine,
      )
    
    # Check if the target needs building
    _, reasonToBuild = engine.checkDependencyInfo(target, args)
    if not reasonToBuild:
      return # Target is up to date
    engine.logger.outputDebug(
      "reason",
      "Rebuilding '" + target + "' because " + reasonToBuild + ".\n",
      )

    targets = [FileInfo(path=target)]
    if object is not None:
      targets.append(FileInfo(path=object))
    newDependencyInfo = DependencyInfo(
      targets=targets,
      args=args,
      dependencies=None,
      )

    # If we get to here then we didn't find the object in the cache
    # so we need to actually execute the build.
    engine.logger.outputInfo("Compiling %s\n" % source)
    compileTask = compile()

    def storeDependencyInfoAndCache():
     
      # Since we are sharing this object in the object cache we need to
      # make any paths in this workspace relative to the current workspace.
      dependencies = []
      if self.objectCacheWorkspaceRoot is None:
        dependencies = [os.path.abspath(p) for p in compileTask.result]
      else:
        workspaceRoot = os.path.normcase(
          os.path.abspath(self.objectCacheWorkspaceRoot)
          ) + os.path.sep
        workspaceRootLen = len(workspaceRoot)
        for path in compileTask.result:
          path = os.path.abspath(path)
          pathNorm = os.path.normcase(path)
          if pathNorm.startswith(workspaceRoot):
            path = path[workspaceRootLen:]
          dependencies.append(path)
      
      getTimestamp = engine.getTimestamp
      
      newDependencyInfo.dependencies = [
        FileInfo(
          path=path,
          timestamp=getTimestamp(path),
          )
        for path in dependencies
        ]
      engine.storeDependencyInfo(newDependencyInfo)
        
    storeDependencyTask = engine.createTask(storeDependencyInfoAndCache)
    storeDependencyTask.startAfter(compileTask, immediate=True)

  def buildObject(self, target, source, pch, engine):
    """Perform the actual build of an object.
    
    @param target: Path of the target object file.
    @type target: string
    
    @param source: Path of the source file.
    @type source: string
    
    @param engine: The build Engine to use when building this object.
    """
    compile, args, canBeCached = self.getObjectCommands(
      target,
      source,
      pch,
      engine,
      )
    
    # Check if the target needs building
    oldDependencyInfo, reasonToBuild = engine.checkDependencyInfo(target, args)
    if not reasonToBuild:
      return # Target is up to date
    engine.logger.outputDebug(
      "reason",
      "Rebuilding '" + target + "' because " + reasonToBuild + ".\n",
      )

    newDependencyInfo = DependencyInfo(
      targets=[FileInfo(path=target)],
      args=args,
      dependencies=None,
      )
      
    useCacheForThisObject = canBeCached and self.objectCachePath is not None
      
    if useCacheForThisObject:
      #######################
      # USING OBJECT CACHE
      #######################
      
      # Prime the file digest cache from previous run so we don't have
      # to recalculate file digests for files that haven't changed.
      if oldDependencyInfo is not None:
        for dep in oldDependencyInfo.dependencies:
          if dep.timestamp is not None and dep.digest is not None:
            engine.updateFileDigestCache(dep.path, dep.timestamp, dep.digest)
      
      # We either need to make all paths that form the cache digest relative
      # to the workspace root or all of them absolute.
      targetDigestPath = os.path.abspath(target)
      if self.objectCacheWorkspaceRoot is not None:
        workspaceRoot = os.path.abspath(self.objectCacheWorkspaceRoot)
        workspaceRoot = os.path.normcase(workspaceRoot)
        targetDigestPathNorm = os.path.normcase(targetDigestPath)
        if cake.path.commonPath(targetDigestPathNorm, workspaceRoot) == workspaceRoot:
          targetDigestPath = targetDigestPath[len(workspaceRoot)+1:]
          
      # Find the directory that will contain all cached dependency
      # entries for this particular target object file.
      targetDigest = cake.hash.sha1(targetDigestPath.encode("utf8")).digest()
      targetDigestStr = binascii.hexlify(targetDigest).decode("utf8")
      targetCacheDir = cake.path.join(
        self.objectCachePath,
        targetDigestStr[0],
        targetDigestStr[1],
        targetDigestStr
        )
      
      # Find all entries in the directory
      entries = set()
      
      # If doing a force build, pretend the cache is empty
      if not engine.forceBuild:
        try:
          entries.update(os.listdir(targetCacheDir))
        except EnvironmentError:
          # Target cache dir doesn't exist, treat as if no entries
          pass
      
      hexChars = "0123456789abcdefABCDEF"
      
      # Try to find the dependency files
      for entry in entries:
        # Skip any entry that's not a SHA-1 hash
        if len(entry) != 40:
          continue
        skip = False
        for c in entry:
          if c not in hexChars:
            skip = True
            break
        if skip:
          continue

        cacheDepPath = cake.path.join(targetCacheDir, entry)
        
        try:
          f = open(cacheDepPath, 'rb')
          try:
            cacheDepContents = f.read()
          finally:
            f.close()
        except EnvironmentError:
          continue
        
        try:
          candidateDependencies = pickle.loads(cacheDepContents)
        except Exception:
          # Invalid dependency file for this entry
          continue
        
        if not isinstance(candidateDependencies, list):
          # Data format change
          continue
        
        try:
          newDependencyInfo.dependencies = [
            FileInfo(
              path=path,
              timestamp=engine.getTimestamp(path),
              digest=engine.getFileDigest(path),
              )
            for path in candidateDependencies
            ]
        except EnvironmentError:
          # One of the dependencies didn't exist
          continue
        
        # Check if the state of our files matches that of a cached
        # object file.
        cachedObjectDigest = newDependencyInfo.calculateDigest(engine)
        cachedObjectDigestStr = binascii.hexlify(cachedObjectDigest).decode("utf8")
        cachedObjectPath = cake.path.join(
          self.objectCachePath,
          cachedObjectDigestStr[0],
          cachedObjectDigestStr[1],
          cachedObjectDigestStr
          )
        if cake.filesys.isFile(cachedObjectPath):
          engine.logger.outputInfo("Cached %s\n" % source)
          cake.filesys.copyFile(
            target=target,
            source=cachedObjectPath,
            )
          engine.storeDependencyInfo(newDependencyInfo)
          return

    # If we get to here then we didn't find the object in the cache
    # so we need to actually execute the build.
    engine.logger.outputInfo("Compiling %s\n" % source)
    compileTask = compile()

    def storeDependencyInfoAndCache():
     
      # Since we are sharing this object in the object cache we need to
      # make any paths in this workspace relative to the current workspace.
      dependencies = []
      if self.objectCacheWorkspaceRoot is None:
        dependencies = [os.path.abspath(p) for p in compileTask.result]
      else:
        workspaceRoot = os.path.normcase(
          os.path.abspath(self.objectCacheWorkspaceRoot)
          ) + os.path.sep
        workspaceRootLen = len(workspaceRoot)
        for path in compileTask.result:
          path = os.path.abspath(path)
          pathNorm = os.path.normcase(path)
          if pathNorm.startswith(workspaceRoot):
            path = path[workspaceRootLen:]
          dependencies.append(path)
      
      getTimestamp = engine.getTimestamp
      getFileDigest = engine.getFileDigest
      
      if useCacheForThisObject:
        # Need to store the file digests to improve performance of
        # cache calculations in subsequent runs.
        newDependencyInfo.dependencies = [
          FileInfo(
            path=path,
            timestamp=getTimestamp(path),
            digest=getFileDigest(path),
            )
          for path in dependencies
          ]
      else:
        newDependencyInfo.dependencies = [
          FileInfo(
            path=path,
            timestamp=getTimestamp(path),
            )
          for path in dependencies
          ]
      engine.storeDependencyInfo(newDependencyInfo)

      # Finally update the cache if necessary
      if useCacheForThisObject:
        try:
          objectDigest = newDependencyInfo.calculateDigest(engine)
          objectDigestStr = binascii.hexlify(objectDigest).decode("utf8")
          
          dependencyDigest = cake.hash.sha1()
          for dep in dependencies:
            dependencyDigest.update(dep.encode("utf8"))
          dependencyDigest = dependencyDigest.digest()
          dependencyDigestStr = binascii.hexlify(dependencyDigest).decode("utf8")
          
          cacheDepPath = cake.path.join(
            targetCacheDir,
            dependencyDigestStr
            )
          cacheObjectPath = cake.path.join(
            self.objectCachePath,
            objectDigestStr[0],
            objectDigestStr[1],
            objectDigestStr,
            )

          # Copy the object file first, then the dependency file
          # so that other processes won't find the dependency until
          # the object file is ready.
          cake.filesys.makeDirs(cake.path.dirName(cacheObjectPath))
          cake.filesys.copyFile(target, cacheObjectPath)
          
          if not cake.filesys.isFile(cacheDepPath):
            cake.filesys.makeDirs(targetCacheDir)
            f = open(cacheDepPath, 'wb')
            try:
              f.write(pickle.dumps(dependencies, pickle.HIGHEST_PROTOCOL))
            finally:
              f.close()
            
        except EnvironmentError:
          # Don't worry if we can't put the object in the cache
          # The build shouldn't fail.
          pass
        
    storeDependencyTask = engine.createTask(storeDependencyInfoAndCache)
    storeDependencyTask.startAfter(compileTask, immediate=True)
  
  def getPchCommands(self, target, source, header, object, engine):
    """Get the command-lines for compiling a precompiled header.
    
    @return: A (compile, args, canCache) tuple where 'compile' is a function that
    takes no arguments returns a task that completes with the list of paths of
    dependencies when the compilation succeeds. 'args' is a value that indicates
    the parameters of the command, if the args changes then the target will
    need to be rebuilt; typically args includes the compiler's command-line.
    'canCache' is a boolean value that indicates whether the built object
    file can be safely cached or not.
    """
    engine.raiseError("Don't know how to compile %s\n" % source)

  def getObjectCommands(self, target, source, pch, engine):
    """Get the command-lines for compiling a source to a target.
    
    @return: A (compile, args, canCache) tuple where 'compile' is a function that
    takes no arguments returns a task that completes with the list of paths of
    dependencies when the compilation succeeds. 'args' is a value that indicates
    the parameters of the command, if the args changes then the target will
    need to be rebuilt; typically args includes the compiler's command-line.
    'canCache' is a boolean value that indicates whether the built object
    file can be safely cached or not.
    """
    engine.raiseError("Don't know how to compile %s\n" % source)
  
  def buildLibrary(self, target, sources, engine):
    """Perform the actual build of a library.
    
    @param target: Path of the target library file.
    @type target: string
    
    @param sources: List of source object files.
    @type sources: list of string
    
    @param engine: The Engine object to use for dependency checking
    etc.
    """

    archive, scan = self.getLibraryCommand(target, sources, engine)
    
    args = repr(archive)
    
    # Check if the target needs building
    _, reasonToBuild = engine.checkDependencyInfo(target, args)
    if not reasonToBuild:
      return # Target is up to date
    engine.logger.outputDebug(
      "reason",
      "Rebuilding '" + target + "' because " + reasonToBuild + ".\n",
      )

    engine.logger.outputInfo("Archiving %s\n" % target)
    
    cake.filesys.makeDirs(cake.path.dirName(target))
    
    archive()
    
    dependencies = scan()
    
    newDependencyInfo = DependencyInfo(
      targets=[FileInfo(target)],
      args=args,
      dependencies=[
        FileInfo(path=path, timestamp=engine.getTimestamp(path))
        for path in dependencies
        ],
      )
    
    engine.storeDependencyInfo(newDependencyInfo)
  
  def getLibraryCommand(self, target, sources, engine):
    """Get the command for constructing a library.
    """
    engine.raiseError("Don't know how to archive %s\n" % target)
  
  def buildModule(self, target, sources, engine):
    """Perform the actual build of a module.
    
    @param target: Path of the target module file.
    @type target: string
    
    @param sources: Paths of the source object files and
    libraries to link.
    @type sources: list of string
    
    @param engine: The Engine object to use for dependency checking
    etc.
    """
    link, scan = self.getModuleCommands(target, sources, engine)

    args = [repr(link), repr(scan)]
    
    # Check if the target needs building
    _, reasonToBuild = engine.checkDependencyInfo(target, args)
    if not reasonToBuild:
      return # Target is up to date
    engine.logger.outputDebug(
      "reason",
      "Rebuilding '" + target + "' because " + reasonToBuild + ".\n",
      )

    engine.logger.outputInfo("Linking %s\n" % target)
  
    link()
  
    dependencies = scan()
    
    newDependencyInfo = DependencyInfo(
      targets=[FileInfo(target)],
      args=args,
      dependencies=[
        FileInfo(path=path, timestamp=engine.getTimestamp(path))
        for path in dependencies
        ],
      )
    
    engine.storeDependencyInfo(newDependencyInfo)
  
  def getModuleCommands(self, target, sources, engine):
    """Get the commands for linking a module.
    
    @param target: path to the target file
    @type target: string
    
    @param sources: list of the object/library file paths to link into the
    module.
    @type sources: list of string
    
    @param engine: The cake Engine being used for the build.
    @type engine: cake.engine.Engine
    
    @return: A tuple (link, scan) representing the commands that perform
    the link and scan for dependencies respectively. The scan command
    returns the list of dependencies. 
    """
    engine.raiseError("Don't know how to link %s\n" % target)
  
  def buildProgram(self, target, sources, engine):
    """Perform the actual build of a module.
    
    @param target: Path of the target module file.
    @type target: string
    
    @param sources: Paths of the source object files and
    libraries to link.
    @type sources: list of string
    
    @param engine: The Engine object to use for dependency checking
    etc.
    """

    link, scan = self.getProgramCommands(target, sources, engine)

    args = [repr(link), repr(scan)]
    
    # Check if the target needs building
    _, reasonToBuild = engine.checkDependencyInfo(target, args)
    if not reasonToBuild:
      return # Target is up to date
    engine.logger.outputDebug(
      "reason",
      "Rebuilding '" + target + "' because " + reasonToBuild + ".\n",
      )

    engine.logger.outputInfo("Linking %s\n" % target)
  
    link()
  
    dependencies = scan()
    
    newDependencyInfo = DependencyInfo(
      targets=[FileInfo(target)],
      args=args,
      dependencies=[
        FileInfo(path=path, timestamp=engine.getTimestamp(path))
        for path in dependencies
        ],
      )
    
    engine.storeDependencyInfo(newDependencyInfo)

  def getProgramCommands(self, target, sources, engine):
    """Get the commands for linking a program.
    
    @param target: path to the target file
    @type target: string
    
    @param sources: list of the object/library file paths to link into the
    program.
    @type sources: list of string
    
    @param engine: The cake Engine being used for the build.
    @type engine: cake.engine.Engine
    
    @return: A tuple (link, scan) representing the commands that perform
    the link and scan for dependencies respectively. The scan command
    returns the list of dependencies. 
    """
    engine.raiseError("Don't know how to link %s\n" % target)
