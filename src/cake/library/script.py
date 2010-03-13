"""Script Tool.

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

from cake.engine import Script, DependencyInfo, FileInfo
from cake.library import Tool, FileTarget, getPathsAndTasks

class ScriptTool(Tool):
  """Tool that provides utilities for performing Script operations.
  """
  
  @property
  def path(self):
    """The path of the currently executing script.
    """
    script = Script.getCurrent()
    if script:
      return script.path
    else:
      return None
  
  @property
  def dir(self):
    """The path of the directory of the currently executing script.
    """
    script = Script.getCurrent()
    if script:
      return script.dir
    else:
      return None
  
  @property
  def engine(self):
    """The Engine the currently executing script belongs to.
    """
    script = Script.getCurrent()
    if script:
      return script.engine
    else:
      return None
  
  @property
  def variant(self):
    """The Variant the currently executing script is being built with.
    """
    script = Script.getCurrent()
    if script:
      return script.variant
    else:
      return None

  def cwd(self, *args):
    """Return the path prefixed with the this script's directory.
    
    Examples::
      env.cwd("a") -> "{cwd}/a"
      env.cwd(["a", "b", "c"]) -> ["{cwd}/a", "{cwd}/b", "{cwd}/c"]
      
    @param args: The arguments that need to have the prefix added.
    @type args: string or list(string)
    
    @return: The path prefixed with this script's directory.
    @rtype: string or list(string)
    """
    script = Script.getCurrent()
    return script.cwd(*args)
    
  def include(self, scripts):
    """Include another script within the context of the currently
    executing script.
    
    A given script will only be included once.
    
    @param scripts: A path or sequence of paths of scripts to include.
    @type path: string or sequence of string
    """
    include = Script.getCurrent().include
    if isinstance(scripts, basestring):
      include(scripts)
    else:
      for path in scripts:
        include(path)
    
  def execute(self, scripts, **keywords):
    """Execute another script as a background task.

    @param scripts: A path or sequence of paths of scripts to execute.
    @type scripts: string or sequence of string

    @return: A task or sequence of tasks that can be used to determine
      when all tasks created by the script have finished executing.
    @rtype: L{Task} or C{list} of L{Task}
    """
    script = Script.getCurrent()
    engine = script.engine
    variant = engine.findVariant(keywords, baseVariant=script.variant)
    execute = engine.execute
    if isinstance(scripts, basestring):
      return execute(scripts, variant)
    else:
      return [execute(path, variant) for path in scripts]

  def run(self, func, args=None, targets=None, sources=[]):
    """Execute the specified python function as a task.

    Only executes the function after the sources have been built and only
    if the target exists, args is the same as last run and the sources
    havent changed.

    @note: I couldn't think of a better class to put this function in so
    for now it's here although it doesn't really belong.
    """
    script = Script.getCurrent()
    engine = script.engine

    sourcePaths, sourceTasks = getPathsAndTasks(sources)

    def _run():

      if targets:
        buildArgs = (args, sourcePaths)
        try:
          oldDependencyInfo = engine.getDependencyInfo(targets[0])
          if oldDependencyInfo.isUpToDate(engine, buildArgs):
            return
        except EnvironmentError:
          pass

      func()

      if targets:
        newDependencyInfo = DependencyInfo(
          targets=[FileInfo(path=t) for t in targets],
          args=buildArgs,
          dependencies=[
            FileInfo(
              path=s,
              timestamp=engine.getTimestamp(s),
              )
            for s in sourcePaths
            ],
          )
        engine.storeDependencyInfo(newDependencyInfo)

    task = engine.createTask(_run)
    task.startAfter(sourceTasks)

    if targets is not None:
      return [FileTarget(path=t, task=task) for t in targets]
    else:
      return task
