#-------------------------------------------------------------------------------
# This example demonstrates how to build a zip file from a source file/directory
# using the ZipTool.
#-------------------------------------------------------------------------------
from cake.tools import zipping

# Function that determines what to include (based on source file/directory path).
def shouldInclude(path):
  return True

# Function that determines what to exclude (based on source file/directory path).
def shouldExclude(path):
  return path.find("exclude") != -1

# Build the zip file. Only update files/directories that are newer than those in
# the zip. Remove any files/directories in the zip that no longer exist in the
# source path. 
zipping.compress(
  target="../build/zip/zip.zip",
  source="zipme",
  onlyNewer=True,
  removeStale=True,
  includeMatch=shouldInclude,
  excludeMatch=shouldExclude,
  )
