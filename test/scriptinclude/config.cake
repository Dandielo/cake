from cake.engine import Variant
from cake.script import Script

from cake.library.script import ScriptTool

configuration = Script.getCurrent().configuration

# Setup the tools we want to use in the build.cake
variant = Variant()
variant.tools["script"] = ScriptTool(configuration=configuration)

configuration.addVariant(variant)
