from pymba import Vimba

with Vimba() as vimba:
    system = vimba.system()
    system.run_feature_command("GeVDiscoveryAllOnce")
