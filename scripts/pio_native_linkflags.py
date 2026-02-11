Import("env")
from SCons.Script import DefaultEnvironment

import platform

pio_env = env.get("PIOENV", "")
if platform.system() == "Windows" and pio_env == "native":
    env.Append(LIBS=["ws2_32"])
    DefaultEnvironment().Append(LIBS=["ws2_32"])
