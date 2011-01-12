"""Running Utilities.

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

import os
import os.path
import sys
import optparse
import threading
import datetime
import time
import traceback
import platform

import cake.logging
import cake.engine
import cake.task
import cake.path
import cake.threadpool

# Make sure stat() returns floats so timestamps are consistent across
# Python versions (2.4 used longs, 2.5+ uses floats).
os.stat_float_times(True)

def callOnce(f):
  """Decorator that handles calling a function only once.

  The second and subsequent times it is called the cached
  result is returned.
  """
  state = {}
  def func(*args, **kwargs):
    if state:
      try:
        return state["result"]
      except KeyError:
        raise state["exception"]
    else:
      try:
        result = state["result"] = f(*args, **kwargs)
        return result
      except Exception, e:
        state["exception"] = e
        raise
  return func 

@callOnce
def _overrideOpen():
  """
  Override the built-in open() and os.open() to set the no-inherit
  flag on files to prevent processes from inheriting file handles.
  """
  if hasattr(os, "O_NOINHERIT"):
    import __builtin__
  
    old_open = __builtin__.open
    def new_open(filename, mode="r", *args, **kwargs):
      if "N" not in mode:
        mode += "N"
      return old_open(filename, mode, *args, **kwargs)
    __builtin__.open = new_open
  
    old_os_open = os.open
    def new_os_open(filename, flag, mode=0777):
      flag |= os.O_NOINHERIT
      return old_os_open(filename, flag, mode)
    os.open = new_os_open

@callOnce
def _overridePopen():
  """
  Override the subprocess Popen class due to a bug in Python 2.4
  that can cause an exception if a process finishes too quickly.
  """
  version = platform.python_version_tuple()
  if version[0] == "2" and version[1] == "4":
    import subprocess
    
    old_Popen = subprocess.Popen
    class new_Popen(old_Popen):
      def poll(self):
        try:
          return old_Popen.poll(self)
        except ValueError:
          return self.returncode
      
      def wait(self):
        try:
          return old_Popen.wait(self)
        except ValueError:
          return self.returncode
    subprocess.Popen = new_Popen

@callOnce    
def _speedUp():
  """
  Speed up execution by importing Psyco and binding the slowest functions
  with it.
  """ 
  try:
    import psyco
    psyco.bind(cake.engine.Configuration.checkDependencyInfo)
    psyco.bind(cake.engine.Configuration.createDependencyInfo)
    #psyco.full()
    #psyco.profile()
    #psyco.log()
  except ImportError:
    # Only report import failures on systems we know Psyco supports.
    version = platform.python_version_tuple()
    supportsVersion = version[0] == "2" and version[1] in ["5", "6"]
    if platform.system() == "Windows" and supportsVersion:
      sys.stderr.write(
        "warning: Psyco is not installed. Installing it may halve your incremental build time.\n"
        )

def run(args=None, cwd=None):
  """Run a cake build with the specified command-line args.
  
  @param args: A list of command-line args for cake. If this is None 
  sys.argv is used instead.
  @type args: list of string, or None
  @param cwd: The working directory to use. If this is None os.getcwd()
  is used instead.
  @type cwd: string or None
  
  @return: The exit code of cake. Non-zero if exited with errors, zero
  if exited with success.
  @rtype: int
  """
  startTime = datetime.datetime.utcnow()
  
  _overrideOpen()
  _overridePopen()
  _speedUp()
  
  if args is None:
    args = sys.argv[1:]

  if cwd is not None:
    cwd = os.path.abspath(cwd)
  else:
    cwd = os.getcwd()

  class MyParser(optparse.OptionParser):
    """Subclass OptionParser to allow us to ignore errors during the initial
    option parsing.
    """
    showErrors = True
    def parse_args(self, args=None, values=None, showErrors=True):
      self.showErrors = showErrors;
      try:
        return optparse.OptionParser.parse_args(self, args, values)
      finally:
        self.showErrors = True;
    def error(self, msg):
      if self.showErrors:
        optparse.OptionParser.error(self, msg);
    
  class MyOption(optparse.Option):
    """Subclass the Option class to provide an 'extend' action.
    """  
    ACTIONS = optparse.Option.ACTIONS + ("extend",)
    STORE_ACTIONS = optparse.Option.STORE_ACTIONS + ("extend",)
    TYPED_ACTIONS = optparse.Option.TYPED_ACTIONS + ("extend",)
    ALWAYS_TYPED_ACTIONS = optparse.Option.ALWAYS_TYPED_ACTIONS + ("extend",)
  
    def take_action(self, action, dest, opt, value, values, parser):
      if action == "extend":
        lvalue = value.split(",")
        values.ensure_value(dest, []).extend(lvalue)
      else:
        optparse.Option.take_action(
          self, action, dest, opt, value, values, parser
          )
        
  usage = "usage: %prog [options] <cake-script>*"
  
  parser = MyParser(usage=usage, option_class=MyOption, add_help_option=False)
  parser.add_option(
    "-V", "--version",
    dest="outputVersion",
    action="store_true",
    help="Print the current version of Cake and exit.",
    default=False,
    )
  parser.add_option(
    "--args",
    metavar="FILE",
    dest="args",
    help="Path to the args.cake file to use.",
    default=None,
    )
  parser.add_option(
    "--config",
    metavar="FILE",
    dest="config",
    help="Path to the config.cake configuration file to use.",
    default=None,
    )
  parser.add_option(
    "--debug", metavar="KEYWORDS",
    action="extend",
    dest="debugComponents",
    help="Set features to debug, eg: 'reason,run,script,scan'.",
    default=[],
    )
  parser.add_option(
    "-s", "--silent", "--quiet",
    action="store_true",
    dest="quiet",
    help="Suppress printing of all Cake messages, warnings and errors.",
    default=False,
    )
  parser.add_option(
    "-f", "--force",
    action="store_true",
    dest="forceBuild",
    help="Force rebuild of every target.",
    default=False,
    )
  parser.add_option(
    "-j", "--jobs",
    metavar="JOBCOUNT",
    type="int",
    dest="jobs",
    help="Number of simultaneous jobs to execute.",
    default=cake.threadpool.getProcessorCount(),
    )
  parser.add_option(
    "-k", "--keep-going",
    dest="maximumErrorCount",
    action="store_const",
    const=None,
    help="Keep building even in the presence of errors.",
    )
  parser.add_option(
    "-e", "--max-errors",
    dest="maximumErrorCount",
    metavar="COUNT",
    type="int",
    help="Halt the build after a certain number of errors.",
    default=100,
    )

  options, _args = parser.parse_args(args, showErrors=False)

  if options.outputVersion:
    cakeVersion = cake.__version__
    cakePath = cake.path.dirName(cake.__file__)
    sys.stdout.write("Cake %s\n" % cake.__version__)
    sys.stdout.write("Python %s\n" % sys.version)
    return 1

  # Find script filenames from the arguments left
  logger = cake.logging.Logger()
  engine = cake.engine.Engine(logger, parser)

  # Find script filenames from the arguments
  scripts = []
  for arg in args:
    if not os.path.isabs(arg):
      arg = os.path.join(cwd, arg)
    # If it's a file or directory assume it's a script path
    if os.path.exists(arg):
      scripts.append(arg)

  # Default to building a script file in the working directory.    
  if not scripts:
    scripts.append(cwd)

  argsFileName = options.args
  if argsFileName is None:
    # Try to find an args.cake by searching up from each scripts directory
    for script in scripts:
      # Script could be a file or directory name
      if os.path.isdir(script):
        scriptDirName = script
      else:
        scriptDirName = os.path.dirname(script)
      argsFileName = engine.searchUpForFile(scriptDirName, "args.cake")

  # Run the args.cake
  if argsFileName is not None:
    script = cake.engine.Script(
      path=argsFileName,
      configuration=None,
      variant=None,
      task=None,
      engine=engine,
      )
    script.execute()

  # Parse again, this time with user options and help/errors enabled
  parser.add_option(
    "-h", "--help",
    action="help",
    help="Show this help message and exit.",
    )
  engine.options, args = parser.parse_args(args)

  # Set components to debug
  for c in options.debugComponents:
    logger.enableDebug(c)

  # Set quiet mode    
  logger.quiet = options.quiet;

  # Find keyword arguments  
  keywords = {}
  for arg in args:
    if '=' in arg:
      keyword, value = arg.split('=', 1)
      value = value.split(',')
      if len(value) == 1:
        value = value[0]
      keywords[keyword] = value
  
  threadPool = cake.threadpool.ThreadPool(options.jobs)
  cake.task.setThreadPool(threadPool)

  engine.forceBuild = options.forceBuild
  engine.maximumErrorCount = options.maximumErrorCount
 
  tasks = []
  
  configScript = options.config
  if configScript is not None and not os.path.isabs(configScript):
    configScript = os.path.abspath(configScript)
  
  bootFailed = False
  
  for script in scripts:
    script = cake.path.fileSystemPath(script)
    try:
      task = engine.execute(
        path=script,
        configScript=configScript,
        keywords=keywords,
        )
      tasks.append(task)
    except cake.engine.BuildError:
      # Error already output
      bootFailed = True
    except Exception:
      bootFailed = True
      msg = traceback.format_exc()
      engine.logger.outputError(msg)
      engine.errors.append(msg)
    
  def onFinish():
    if not bootFailed and mainTask.succeeded:
      engine.onBuildSucceeded()
      if engine.warningCount:
        msg = "Build succeeded with %i warnings.\n" % engine.warningCount
      else:
        msg = "Build succeeded.\n"
    else:
      engine.onBuildFailed()
      if engine.warningCount:
        msg = "Build failed with %i errors and %i warnings.\n" % (
          engine.errorCount,
          engine.warningCount,
          )
      else:
        msg = "Build failed with %i errors.\n" % engine.errorCount
    engine.logger.outputInfo(msg)
  
  mainTask = cake.task.Task()
  mainTask.completeAfter(tasks)
  mainTask.addCallback(onFinish)
  mainTask.start()

  finished = threading.Event()
  mainTask.addCallback(finished.set)
  # We must wait in a loop in case a KeyboardInterrupt comes.
  while not finished.isSet():
    time.sleep(0.1)
  
  endTime = datetime.datetime.utcnow()
  engine.logger.outputInfo("Build took %s.\n" % (endTime - startTime))
  
  return engine.errorCount
