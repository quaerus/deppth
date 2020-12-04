# deppth
Decompress, Extract, and Pack for Pyre, Transistor, and Hades.

Deppth is a high-level I/O interface for package files in the games Transistor, Pyre, and Hades. Deppth provides both command-line and programmer interfaces.

## Installation

To install Deppth, download the latest [wheel](https://github.com/quaerus/deppth/releases) and `pip install` it. Then read the following instructions to install dependencies.

### Dependencies

Deppth technically has no required dependencies outside of Python's core modules, but you may find its functionality very limited without also installing the following optional dependencies. If an optional dependency is missing, Deppth will abort an operation dependent on that module informing you of the missing module.

Packages primarily contain sprite sheets. Deppth uses Pillow to work with the image data within. If you plan to export/import sprite sheets to/from image files, you'll need to install that: `pip install pillow`.

Hades uses LZ4 compression on its packages. If you plan to work with these packages, you'll want to install the LZ4 module: `pip install lz4`.

Transistor and Pyre both use LZF compression on their packages. If you plan to work with these packages, you'll want to install the LZF module: `pip install lzf`. You may need to install C++ build tools to get this dependency to install correctly.

## CLI Quick-Start

Let's say we want to edit a spritesheet in Launch.pkg. First, we'll want to **extract** the package to get the individual assets out.

    deppth ex Launch.pkg

This will create a folder called Launch in the current working directory. The texture atlases will be in the textures/atlases directory within there.

Let's say I edit Launch_Textures02.png. Now, to rebuild the package, I'll want to **pack** this folder into a package again.

    deppth pk -s Launch -t Launch.pkg

If I then replace the package file in the game files with this package file, it should use my updated asset. But, suppose I'm trying to distribute a mod. I probably only want to distribute my change to the package, not the entire package. In that case, you probably want to build a patch for someone else to apply.

To do this, you can use the **pack** command with the **entries** flag to only include any items you changed (this works similar to patterns in other CLI tools).

    deppth pk -s Launch -t Launch_patch.pkg -e *Launch_Textures02*

I can then distribute Launch_patch.pkg and Launch_patch.pkg_manifest. To apply this patch to the actual package, one would need to place these files in the same folder and then use the **patch** command to perform the patching. 

     deppth pt Launch.pkg Launch_patch.pkg

This will replace any entries in the package with any matching entries in the patches and append any new entries in the patches. More than one patch can be applied at a time (later ones take precedence if there are conflicts).

 ## Deppth API

The Deppth module exposes functions that perform the actions described above, plus a fourth (which is also part of the CLI) to list the contents of a package. It's basically just a programmer interface for the same things the CLI does -- the latter is just a wrapper for the former.

    list_contents(name, *patterns, logger=lambda  s: None)
    extract(package, target_dir, *entries, subtextures=False, logger=lambda  s: None)
    pack(source_dir, package, *entries, logger=lambda  s: None)
    patch(name, *patches, logger=lambda  s : None)

The logger kwarg allows for customization of output of these functions -- for example, you may want to write to a file instead of print to screen.

## SGGPIO

The SGGPIO module is a lower-level interface for working with packages. The aim is to provide IO-esque streams to read and write package data. Most users won't need this, but for certain applications, using it could lead to better performance or more customizable behavior.

SGGPIO exports two functions, which really just wrap functionality in a variety of reader and writer classes. I recommend reading the docs on these classes if you're interested, but basic usage looks something like this.

    from deppth import sggpio

    # Copy Launch.pkg and corresponding manifest
    with sggpio.open_package('Launch.pkg', 'rm') as pkg:
	    with sggpio.open_package('Launch_copy.pkg', 'wm') as pkg_out:
		    for entry in pkg:
			    pkg_out.write_entry_with_manifest(entry)
	
	# Print manifest contents of copy to verify success
	with sggpio.open_package('Launch_copy.pkg', 'rm') as pkg:
		for entry in pkg.manifest:
			print(entry)

    

