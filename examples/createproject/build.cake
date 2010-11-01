#-------------------------------------------------------------------------------
# This example demonstrates creating a project and solution using the project
# tool.
#
# Note that the example must be run with '-p' or '--projects' on the command
# line to generate the projects.
#-------------------------------------------------------------------------------
from cake.tools import script, project

# Build the solution. Use the 'project' result of the main programs build.cake
# as one of the solutions project files.
project.solution(
  target=script.cwd("../build/createproject/project/createproject"),
  projects=[
    script.getResult(script.cwd("main/build.cake"), "project"),
    ],
  )
