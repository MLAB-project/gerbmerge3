# gerbmerge3

This project is a fork of the original [Gerbmerge program](http://www.ruggedcircuits.com/gerbmerge/) created by Rugged Circuits (last release version 1.8 on June 8th, 2011). Gerbmerge originally required Python 2.x along with the SimpleParse library (also only available for Python 2.x).

I originally decided to fork Gerbmerge to remove the dependency on SimpleParse as well as to update it to Python 3.x. The lack of both of these features made installation/running Gerbmerge a pain. These early plans have since been amended with the following goals:
 * To parallelize the search to span multiple processes to speed up searches
 * To offer a graphical view of the search as it runs and when it ends
 * To generate or use an existing Gerber parser/writer library
 * To simplify and make more Pythonic the codebase

During my evaluation of Gerbmerge and any updates that may have occured out-of-band, I found the [gerbmerge-patched project](https://github.com/space-age-robotics/gerbmerge-patched). It added the ability to add custom text between boards in the panel. Useful when ordering and you want to put an order number on them.

## Usage
gerbmerge can be used in three primary ways: to generate an optimal panelization of a given set of boards or to panelize a manually-specified layout (either in absolute or relative terms).

### Automatic layout
(when run from the included testdata/ directory of gerbmerge)
`$ python ../gerbmerge/gerbmerge.py layout2.cfg --search-timeout 60`

This runs the panelization described in `layout2.cfg` with a 60s limit on how long it can run. The output files are specified in layout2.cfg but will also be listed at the end of the run. Note that this layout will be output into `placement.merge2.xml`, which can be fed in as a manual layout if the panelized gerbers are somehow misplaced.

### Manual layout (relative)
(when run from the included testdata/ directory of gerbmerge)
`$ python ../gerbmerge/gerbmerge.py layout2.cfg layout2.xml`

The layout file `layout2.xml` specifies a relative layout for the panels. The absolute position of all of the panels are calculated by gerbmerge and then output. The absolute positioning will again be output as `placement.merge2.xml` as that is specified in the configuration file.

### Manual layout (absolute)
(when run from the included testdata/ directory of gerbmerge)
`$ python ../gerbmerge/gerbmerge.py layout2.cfg placement.merge2.xml`

The layout file `placement.merge2.xml` is generated during any successful gerbmerge run with the `layout2.cfg` file, so it should exist if you're run the previous two examples, otherwise run them before trying this.

This run specifies an absolute positioning of all boards and the final result is output. This will probably rarely be done, but can be useful with version control if you merely want to reuse this file instead of storing all of the resultant Gerber files.

## Configuration

Configuration of gerbmerge is done through a single `.cfg` file. This is the primary input to gerbmerge, though layout files may be specified for manual positioning. It follows the standard `.ini`-file way of describing options (which is further detailed in the [Python documentation](docs.python.org/3/library/configparser.html). This should be familiar to many POSIX sysadmins or people who have worked with PHP or Apache.

For details on all possible options please consult the existing [gerbmerge documentation](http://www.ruggedcircuits.com/gerbmerge/cfgfile.html).

The configuration file is separated into several sections as defined below:
 * DEFAULT: Defines default values.
 * Options: Defines the various parameters of this panelization.
 * MergeOutputFiles: Defines the naming for the output files
 * BOARD_NAME: Each board used in the panelization has its own section and these follow in alphabetical order.

### DEFAULT
The first section should be the section labeled [DEFAULT]. No variables are required to have been specified here, though setting a common project directory and output naming prefix is common. These and additional variables can be used as text macros for use in setting the values of other variables (note that variable names are NOT case-sensitive!). For example if you create a variable `MergeOut` then you can use the value of this variable later on by specifying `%(mergeout)`.

### Options
The options section specifies all general options for this board run. This includes settings for Excellong/Gerber files and layer options.

### MergeOutputFiles
This section defines the various files that will be generated after this run.

### BOARD_NAME
This really refers to multiple sections, each describing a single board. Generally these only specify the files defining this board as well as a Repeat option if automated placement will occur.

## Layouts
Layouts are specified in `.xml` files and follow the general XML 1.0 specification with one exception: the beginning of the file can have any number of lines starting with `#`. This means that proper XML files are still useable though these layout files may not validate as XML 1.0 (the example `layout1.xml` and `layout2.xml` files will not). These special Python-style comments compliment the existing inline comments available in XML using `<!-- COMMENT -->` syntax.

The XML document contains one root `<panel>` element. Within this element there can be `<row>`, `<col>`, or `<board>` elements. `<row>` can only contain `<col>` or `<board>` and `<col>` can only contain `<row>` or `<board>`.

The `<board>` element have 4 possible attributes:
 * name: The name of this circuit board. It should have a correspondingly-named section in use `.cfg` file.
 * rotation: The number of degrees to rotate this board. Right now the only options are 0, 90, 180, or 270.
 * x: The horizontal x-position of the board specified in decimal inches.
 * y: The vertical y-position of the board specified in decimal inches.

Note that both the row/col and x/y layout of boards conflict. For now all `.xml` layout files should use either a relative row/col layout or an absolute x/y layout and not attempt to mix them as the results are untested and may be ridiculous.

As of right now the XML documents are not validated at all. That means that relative and absolute positioning can be mixed, the doctype can be missing, etc. So if you see weird positioning generated by gerbmerge, check your layout files first.

### Example relative layout
	# This layout merges a Hexapod and Proj1 boards into a single
	# panel.
	<panel>
		<row>
		  <board name="Hexapod" />
		  <col>
			<row>
				<board name="Proj1" rotation="90" />
				<board name="Proj1" rotation="90" />
			</row>
			<row>
				<board name="Proj1" rotation="90" />
				<board name="Proj1" rotation="90" />
			</row>
		  </col>
		</row>
		<row>
			<board name="Proj1" />
			<board name="Proj1" />
			<board name="Proj1" />
		</row>
	</panel>

### Example absolute layout
	<?xml version="1.0" ?>
	<panel>
		<board name="Hexapod" rotation="90" x="0.3000" y="0.3000"/>
		<board name="Proj1" rotation="90" x="3.5746" y="0.3000"/>
		<board name="Proj1" rotation="90" x="4.639200000000001" y="0.3000"/>
		<board name="Proj1" rotation="90" x="3.5746" y="1.4720"/>
		<board name="Proj1" rotation="90" x="4.639200000000001" y="1.4720"/>
		<board name="Proj1" rotation="90" x="3.5746" y="2.644"/>
	</panel>
