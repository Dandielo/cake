"""File System Utilities.

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

import shutil
import os
import os.path
import time

import cake.path

def toUtc(timestamp):
  """Convert a timestamp from local time-zone to UTC.
  """
  return time.mktime(time.gmtime(timestamp))
  
def exists(path):
  """Check if a file or directory exists at the path.
  
  @param path: The path to check for.
  @type path: string
  
  @return: True if a file or directory exists, otherwise False.
  @rtype: bool
  """
  return cake.path.exists(path)

def isFile(path):
  """Check if a file exists at the path.
  
  @param path: The path of the file to check for.
  @type path: string
  
  @return: True if the file exists, otherwise False.
  @rtype: bool
  """
  return cake.path.isFile(path)

def isDir(path):
  """Check if a directory exists at the path.

  @param path: The path of the directory to check for.
  @type path: string
  
  @return: True if the directory exists, otherwise False.
  @rtype: bool
  """
  return cake.path.isDir(path)

def remove(path):
  """Remove a file.
  
  Unlike os.remove() this function fails silently if the
  file does not exist.

  @param path: The path of the file to remove.
  @type path: string
  """
  try:
    os.remove(path)
  except EnvironmentError:
    # Ignore failure if file doesn't exist. Fail if it's a directory.
    if os.path.exists(path):
      raise

def removeTree(path):
  """Recursively delete all files and directories at the specified path.

  Unlike os.removedirs() this function stops deleting entries when
  the specified path and all it's children have been deleted.
  
  os.removedirs() will continue deleting parent directories if they are
  empty.

  @param path: Path to the directory containing the tree to remove
  """
  for root, dirs, files in os.walk(path, topdown=False):
    for name in files:
      p = os.path.join(root, name)
      remove(p)
    for name in dirs:
      p = os.path.join(root, name)
      os.rmdir(p)
  os.rmdir(path)
  
def copyFile(source, target):
  """Copy a file from source path to target path.
  
  Overwrites the target path if it exists and is writeable.
  
  @param source: The path of the source file.
  @type source: string
  @param target: The path of the target file.
  @type target: string
  """
  shutil.copyfile(source, target)

def renameFile(source, target):
  """Rename a file.
  
  Unlike os.rename() if the file exists it is replaced.

  @param source: The path of the source file.
  @type source: string
  @param target: The path of the target file.
  @type target: string
  """
  try:
    os.rename(source, target)
    return # Success
  except EnvironmentError:
    # Remove any existing file with the same name
    remove(target)
  
  # Note: When compiling small programs it is common to get a 'Permission denied'
  # exception here. Presumably it's because the OS has a handle to the destination
  # file open after we have called os.remove(). For this reason we sit in a loop
  # attempting to rename until we reach a timeout of 1 second. However I've
  # noticed under Python 2.4 it's still possible to get 'Permission denied'
  # errors the first time the examples are built. 
  timeout = time.clock() + 1.0
  while True:
    try:
      os.rename(source, target)
      break
    except EnvironmentError:
      if time.clock() >= timeout:
        raise
      time.sleep(0.05)

def makeDirs(path):
  """Recursively create directories.
  
  Unlike os.makedirs(), it does not throw an exception if the
  directory already exists.
  
  @param path: The path of the directory to create.
  @type path: string 
  """
  # Don't try to create directory at the root level, eg: 'C:\\'
  if cake.path.isMount(path):
    return
  
  head, tail = os.path.split(path)
  if not tail:
    head, tail = os.path.split(head)
  if head and tail and not os.path.exists(head):
    makeDirs(head)
    if tail == os.curdir: # xxx/newdir/. exists if xxx/newdir exists
      return

  try:
    os.mkdir(path)
  except EnvironmentError:
    # Ignore failure due to directory already existing.
    if not os.path.isdir(path):
      raise

def walkTree(path, recursive=True):
  """Walk a directory for file and directory names.

  @param path: The path of the directory to search under.
  @param recursive: Whether or not to recursively walk through
  sub-directories.

  @return: A sequence of file and directory paths relative
  to the specified directory path.
  """
  if recursive:
    firstChar = len(path) + 1
    for dirPath, dirNames, fileNames in os.walk(path):
      dirPath = dirPath[firstChar:] # Make dirPath relative to path
      
      for name in dirNames:
        if dirPath:
          yield os.path.join(dirPath, name)
        else:
          yield name

      for name in fileNames:
        if dirPath:
          yield os.path.join(dirPath, name)
        else:
          yield name
  else:
    for name in os.listdir(path):
      yield name
          
def readFile(path):
  """Read data from a file as safely as possible.

  @param path: The path of the file to read.
  @type path: string 
  """
  f = open(path, "rb")
  try:
    return f.read()
  finally:
    f.close()
  
def writeFile(path, data):
  """Write data to a file as safely as possible.

  @param path: The path of the file to write.
  @type path: string 
  @param data: The data to write to the file.
  @type data: string 
  """
  makeDirs(os.path.dirname(path))

  tmpPath = path + ".tmp"
  
  f = open(tmpPath, "wb")
  try:
    f.write(data)
  finally:
    f.close()

  renameFile(tmpPath, path)
