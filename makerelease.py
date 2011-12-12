"""Make release script.

This script will generate the docs and supported install packages
for the current release version (see cake.version.__version__).

@see: Cake Build System (http://sourceforge.net/projects/cake-build)
@copyright: Copyright (c) 2010 Lewis Baker, Stuart McMahon.
@license: Licensed under the MIT license.
"""

import sys
import os
import os.path
import subprocess

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
  if os.path.exists(path):
    os.rmdir(path)

if __name__ == "__main__":
  # Directory to search for python installs.
  installDir = "F:\\Tools"
  
  # Python versions used to build 2x and 3x install packages.
  packageVariants = [
      "Python27",
      "Python32",
    ]
  
  # TODO: Python versions to test with.
  pythonVersions = [
    "Python24",
    "Python25",
    "Python26",
    "Python27",
    "Python30",
    "Python31",
    "Python32",
    ]

  # Commands to build each package.
  packages = [
    ["setup.py", "bdist_wininst", "--plat-name=win32"],
    ["setup.py", "bdist_wininst", "--plat-name=win-amd64"],
    ["setup.py", "sdist", "--formats=gztar,zip"],
    ]

  # Build each package.
  for v in packageVariants:
    pythonExe = os.path.join(installDir, v, "python.exe")

    for p in packages:
      retCode = subprocess.call([pythonExe] + p + ["--dist-dir=dist\\%s" % v])

      # Delete the temporary dirs created by setuptools because they can contaminate builds.
      removeTree("build")
      removeTree("Cake.egg-info")

      if retCode != 0:
        sys.stderr.write("Package '%s' failed to build with code: %d\n" % (" ".join(p), retCode))
  
  # TODO:
  #docs.run()

  sys.exit(0)
