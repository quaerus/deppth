# deppth
Decompress, Extract, and Pack for Pyre, Transistor, and Hades.

Deppth is a high-level I/O interface for package files in the games Transistor, Pyre, and Hades. Deppth itself is presented as a command-line interface for basic tasks like extraction. Contained within the Deppth package is the SGGPIO (SuperGiant Games Package IO) module, which is what programmers should use to interface with Deppth instead of programmatically running the CLI.

## Installation

To install Deppth, download the latest [wheel](https://github.com/quaerus/deppth/releases) and `pip install` it. Then read the following instructions to install dependencies.

### Dependencies

Deppth technically has no required dependencies outside of Python's core modules, but you may find its functionality very limited without also installing the following optional dependencies. If an optional dependency is missing, Deppth will abort an operation dependent on that module informing you of the missing module.

Packages primarily contain sprite sheets. Deppth uses Pillow to work with the image data within. If you plan to export/import sprite sheets to/from image files, you'll need to install that: `pip install pillow`.

Hades uses LZ4 compression on its packages. If you plan to work with these packages, you'll want to install the LZ4 module: `pip install lz4`.

Transistor and Pyre both use LZF compression on their packages. If you plan to work with these packages, you'll want to install the LZF module: `pip install lzf`. You may need to install C++ build tools to get this dependency to install correctly.

## Command-line Usage

Installing Deppth should make it available at a command prompt. Navigate to a Packages directory in one of the supported games and then run one or more of these commands:

### List (ls)

    deppth list pkg_path [patterns]
Lists the contents of the package. This can be used to filter down other calls to target only the entries of the package you're interested in.

If a package contains sprite sheets, which most do, then the subtexture names will also be displayed

*pkg_path*: Should be a path to the package, without the .pkg extension.
*patterns*: Only the entries matching the pattern will be displayed. Currently, this won't apply to the subtextures, however.

Example usage:

    C:\Program Files (x86)\Steam\steamapps\common\Hades\Content\Win\Packages>deppth ls ZeusUpgrade *Nova02
    bin\Win\Atlases\ZeusUpgrade_ZeusLightningStrikeGroundNova02
    Fx\BoonDissipateA\BoonDissipateA0007
    Fx\BoonDissipateA\BoonDissipateA0017
    Fx\BoonDissipateA\BoonDissipateA0016
    Fx\BoonDissipateArrow\AresWrathArrow0013
    Fx\BoonDissipateA\BoonDissipateA0005
    Fx\BoonDissipateA\BoonDissipateA0014
    Fx\BoonDissipateA\BoonDissipateA0015
### Extract (ex)

    deppth extract [-t target] [-e entries] [-s] pkg_path

Extracts the contents of a package.

*pkg_path*: Should be a path to the package, without the .pkg extension.
*target*: Where to extract the package. By default, will create a folder in the current folder with the same name as the package.
*entries*: One or more patterns to filter which entries get extracted. This filter is currently applied only to the entry names, not subtexture names.
*--subtextures*: If this flag is passed, subtextures of sprite sheets will be exported. By default, entire sprite sheets will be exported.

The extraction process will create a folder with one or more subfolders containing the contents:

 - manifest: This folder contains metadata on the contents, such as which rectangles in a sprite sheet represent individual sprites.
 - textures: Sprites and 3D-textures will be exported here
 - spines: Pyre has some assets created by Spine. Those will be exported here.
 - bink_refs: This file contains references to bink files (not the actual bink files, those are elsewhere in the game structure).

These folders may contain subfolders organizing the output. I recommend just trying this out and taking a look yourself.

    deppth ex ZeusUpgrade -s

 ## SGGPIO

The public interface for this is not quite ready for consumption yet, so this space is mostly blank for now. I'm working on it, I promise! In the meantime, check out the source code and documentation (download the docs folder and open sggpio.html in a browser) for an idea of what this can do.


    

