# Stop using this for now
UPDATE: Check out [HEIO](https://hedge-dev.github.io/HedgehogEngineBlenderIO/index.html) for an alternative native model importer with more file support, better documentation, and less issues. This tool is now obsolete.

For animation imports and exports, use the [FrontiersAnimDecompress Blender addon](https://github.com/WistfulHopes/FrontiersAnimDecompress). It supports both compressed and uncompressed *.anm.pxd files with more stability and with correct scaling, as well as standalone *.skl.pxd importing.

For a more general purpose model extraction, use [modelfbx.exe from Dario's LibGens](https://github.com/DarioSamo/libgens-sonicglvl/) to convert .model files to .fbx, which should continue to work on any version of Blender.
.

.

.

Original:
## Hedgehog Engine 2 Importer
A basic blender script to import meshes from games using the engine. Code is still a bit WIP but has been tested on Sakura Wars,Sonic Forces, and Sonic & Mario 2020 Olympics.


For the animation script, select the rig before running the import.
