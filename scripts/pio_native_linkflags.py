Import("env")
from SCons.Script import DefaultEnvironment

import platform

pio_env = env.get("PIOENV", "")
if pio_env == "native":
    if platform.system() == "Windows":
        env.AppendUnique(CPPDEFINES=["ENV_WINDOWS"])
        env.AppendUnique(LIBS=["ws2_32"])
        DefaultEnvironment().AppendUnique(LIBS=["ws2_32"])
    else:
        env.AppendUnique(CPPDEFINES=["ENV_UNIX"])
