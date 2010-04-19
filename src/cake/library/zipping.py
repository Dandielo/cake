"""Zip Tool.

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

from cake.library import Tool, getPathAndTask
import cake.filesys
import zipfile
import os
import os.path
import time
try:
  import cStringIO as StringIO
except ImportError:
  import StringIO

def _extractFile(engine, zipFile, zipPath, zipInfo, targetDir, absTargetDir, onlyNewer):
  """Extract the ZipInfo object to a physical file at targetDir.
  """
  targetFile = os.path.join(targetDir, zipInfo.filename)
  absTargetFile = os.path.join(absTargetDir, zipInfo.filename)
  
  if zipInfo.filename[-1] == '/':
    # The zip info corresponds to a directory.
    cake.filesys.makeDirs(absTargetFile)
  else:
    # The zip info corresponds to a file.
    year, month, day, hour, minute, second = zipInfo.date_time
    zipTime = time.mktime(time.struct_time((year, month, day, hour, minute, second, 0, 0, 0)))
    
    if onlyNewer and os.path.isfile(absTargetFile):
      mtime = os.stat(absTargetFile).st_mtime
      if zipTime == mtime:
        # Assume the zip and the extract are the same file.
        return
    
    engine.logger.outputInfo("Extracting %s\n" % targetFile)
    
    try:
      cake.filesys.writeFile(absTargetFile, zipFile.read(zipInfo.filename))
    except Exception, e:
      engine.raiseError(
        "Failed to extract file %s from zip %s: %s\n" % (
          zipInfo.filename,
          zipPath,
          str(e),
          ),
        )

    # Set the file modification time to match the zip time
    os.utime(absTargetFile, (zipTime, zipTime))

def _writeFile(engine, file, sourcePath, absSourcePath, targetZipPath, targetFilePath):
  sourceFilePath = os.path.join(sourcePath, targetFilePath)
  absSourceFilePath = os.path.join(absSourcePath, targetFilePath)
  targetFilePath = targetFilePath.replace("\\", "/") # Zips use forward slashes
  utcTime = time.gmtime(os.stat(absSourceFilePath).st_mtime)
  
  engine.logger.outputInfo("Adding %s to %s\n" % (sourceFilePath, targetZipPath))
  
  if os.path.isdir(absSourceFilePath):
    if not targetFilePath.endswith("/"):
      targetFilePath += "/" # Trailing slash denotes directory for some zip packages

    zi = zipfile.ZipInfo(targetFilePath, utcTime[0:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0x00000010L # FILE_ATTRIBUTE_DIRECTORY
    file.writestr(zi, "")
  else:  
    f = open(absSourceFilePath, "rb")
    try:
      data = f.read()
    finally:
      f.close()
    
    zi = zipfile.ZipInfo(targetFilePath, utcTime[0:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0x00000020L # FILE_ATTRIBUTE_ARCHIVE
    file.writestr(zi, data)

def _walkTree(path):
  """Recursively walk a directory tree.
  """
  for dirPath, dirNames, fileNames in os.walk(path):
    for name in dirNames:
      yield os.path.join(dirPath, name)
      
    for name in fileNames:
      yield os.path.join(dirPath, name)

class ZipTool(Tool):
  
  def extract(
    self,
    targetDir,
    source,
    onlyNewer=True,
    removeStale=False,
    includeMatch=None,
    excludeMatch=None,
    ):
    """Extract all files in a Zip to the specified path.
  
    @param targetDir: The directory to extract files to.
    @type targetDir: string
    @param source: Path to the zip file to extract files from.
    @type source: string
    @param onlyNewer: Only extract files that are newer than those in
    the target directory.
    @type onlyNewer: bool
    @param removeStale: Remove files and directories in the target
    directory that no longer exist in the zip.
    @type removeStale: bool 
    @param includeMatch: A callable used to decide whether to include
    certain files in the extraction. This could be a python callable that
    returns True to include the file or False to exclude it, or a regular
    expression function such as re.compile().match or re.match.
    @type includeMatch: any callable 
    @param excludeMatch: A callable used to decide whether to exclude certain
    files from being extracted. This could be a python callable that
    returns True to exclude the file or False to include it, or a regular
    expression function such as re.compile().match or re.match.
    @type excludeMatch: any callable 
    
    @return: A task that will complete when the extraction has finished.
    @rtype: L{Task} 
    """
    if not isinstance(targetDir, basestring):
      raise TypeError("targetDir must be a string")

    sourcePath, sourceTask = getPathAndTask(source)

    engine = self.engine
    configuration = self.configuration
    
    def doIt():
      absTargetDir = configuration.abspath(targetDir)
      file = zipfile.ZipFile(configuration.abspath(sourcePath), "r")
      try:
        zipInfos = file.infolist()
        
        if includeMatch is not None:
          newZipInfos = []
          for zipInfo in zipInfos:
            if includeMatch(zipInfo.filename):
              newZipInfos.append(zipInfo)
          zipInfos = newZipInfos

        if excludeMatch is not None:
          newZipInfos = []
          for zipInfo in zipInfos:
            if not excludeMatch(zipInfo.filename):
              newZipInfos.append(zipInfo)
          zipInfos = newZipInfos
        
        if removeStale:
          zipFiles = set()
          for zipInfo in zipInfos:
            zipFiles.add(os.path.normcase(os.path.normpath(zipInfo.filename)))
          
          firstChar = len(absTargetDir) + 1
          for absPath in _walkTree(absTargetDir):
            path = absPath[firstChar:] # Strip the search dir name
            if os.path.normcase(path) not in zipFiles:
              engine.logger.outputInfo(
                "Deleting %s\n" % os.path.join(targetDir, path),
                )
              if os.path.isdir(absPath):
                cake.filesys.removeTree(absPath)
              else:
                cake.filesys.remove(absPath)
        
        for zipinfo in zipInfos:
          _extractFile(engine, file, sourcePath, zipinfo, targetDir, absTargetDir, onlyNewer)   
      finally:
        file.close()

    task = engine.createTask(doIt)
    task.startAfter(sourceTask)
    return task

  def compress(
    self,
    target,
    source,
    onlyNewer=True,
    removeStale=True,
    includeMatch=None,
    excludeMatch=None,
    ):
    """Extract all files in a Zip to the specified path.
  
    @param target: Path to the zip file to add files to.
    @type target: string
    @param source: Path to the source file or directory to add.
    @type source: string
    @param onlyNewer: Only add files that are newer than those in
    the zip file. Otherwise all files are re-added every time.
    @type onlyNewer: bool
    @param removeStale: Remove files and directories in the zip
    file that no longer exist in the source directory.
    @type removeStale: bool 
    @param includeMatch: A callable used to decide whether to include
    certain files in the zip file. This could be a python callable that
    returns True to include the file or False to exclude it, or a regular
    expression function such as re.compile().match or re.match.
    @type includeMatch: any callable 
    @param excludeMatch: A callable used to decide whether to exclude certain
    files from the zip file. This could be a python callable that
    returns True to exclude the file or False to include it, or a regular
    expression function such as re.compile().match or re.match.
    @type excludeMatch: any callable 
    
    @return: A task that will complete when the compression has finished.
    @rtype: L{Task} 
    """
    if not isinstance(target, basestring):
      raise TypeError("target must be a string")

    sourcePath, sourceTask = getPathAndTask(source)

    engine = self.engine
    configuration = self.configuration
    
    def doIt():
      absSourcePath = configuration.abspath(sourcePath)
      absTargetPath = configuration.abspath(target)

      # Build a list of files/dirs to zip
      toZip = {}
      if os.path.isdir(absSourcePath):
        firstChar = len(absSourcePath)+1
        for path in _walkTree(absSourcePath):
          path = path[firstChar:] # Strip the search dir name
          if includeMatch is not None and not includeMatch(path):
            continue
          if excludeMatch is not None and excludeMatch(path):
            continue
          toZip[os.path.normcase(path)] = path
      else:
        toZip[os.path.normcase(path)] = ""
      
      if onlyNewer:
        recreate = False
      else:
        recreate = True # Always rebuild
      
      if not recreate:
        # Try to open an existing zip file
        try:
          file = zipfile.ZipFile(absTargetPath, "r")
          try:
            zipInfos = file.infolist()
          finally:
            file.close()
          
          # Build a list of files/dirs in the current zip
          fromZip = {}
          for zipInfo in zipInfos:
            path = os.path.normpath(os.path.normcase(zipInfo.filename))
            fromZip[path] = zipInfo
        except EnvironmentError:
          recreate = True # File doesn't exist or is invalid

      if not recreate and onlyNewer:
        for casedPath in toZip.iterkeys():
          zipInfo = fromZip.get(casedPath, None)

          # Not interested in modified directories
          if zipInfo is not None and not zipInfo.filename.endswith("/"):
            absSourceFilePath = os.path.join(absSourcePath, casedPath)
            utcTime = time.gmtime(os.stat(absSourceFilePath).st_mtime)
            zipTime = utcTime[0:5] + (
              utcTime[5] & 0xFE, # Zip only saves 2 second resolution
              )              
            if zipTime != zipInfo.date_time:
              # We must recreate the zip to update files
              recreate = True
              break
          
        if not recreate and removeStale:
          for path in fromZip.iterkeys():
            if path not in toZip:
              # We must recreate the zip to remove files
              recreate = True
              break
      
      buffer = None
      fileData = None
      file = None
      try:
        if recreate:
          buffer = StringIO.StringIO()
          file = zipfile.ZipFile(buffer, "w")
          for originalPath in toZip.itervalues():
            _writeFile(engine, file, sourcePath, absSourcePath, target, originalPath)
        else:
          for casedPath, originalPath in toZip.iteritems():
            if casedPath not in fromZip:
              if file is None:
                oldData = cake.filesys.readFile(absTargetPath)
                buffer = StringIO.StringIO(oldData)
                file = zipfile.ZipFile(buffer, "a")
                # Create a new buffer that can be written to
                newBuffer = StringIO.StringIO()
                try:
                  # Write up to start_dir (where zipfile expects to be)
                  newBuffer.write(oldData[:file.start_dir])
                  # Poke into ZipFile to set the new buffer
                  file.fp = newBuffer
                  newBuffer = buffer # Swap old buffer ptr, it will close() below
                  buffer = file.fp 
                finally:
                  newBuffer.close()
              _writeFile(engine, file, sourcePath, absSourcePath, target, originalPath)
      finally:
        if file is not None:
          file.close()
        if buffer is not None:
          fileData = buffer.getvalue()
          buffer.close()
      
      if fileData is not None:
        cake.filesys.writeFile(absTargetPath, fileData)

    task = engine.createTask(doIt)
    task.startAfter(sourceTask)
    return task
    