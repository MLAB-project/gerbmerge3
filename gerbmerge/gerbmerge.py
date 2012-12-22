#!/usr/bin/env python
"""
Merge several RS274X (Gerber) files generated by Eagle into a single
job.

This program expects that each separate job has at least three files:
  - a board outline (RS274X)
  - data layers (copper, silkscreen, etc. in RS274X format)
  - an Excellon drill file

Furthermore, it is expected that each job was generated by Eagle
using the GERBER_RS274X plotter, except for the drill file which
was generated by the EXCELLON plotter.

This program places all jobs into a single job.

--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""

import sys
import os
import argparse
import re

import aptable
import jobs
import config
import parselayout
import fabdrawing
import makestroke
import strokes
import tiling
import tilesearch1
import tilesearch2
import placement
import schwartz
import util
import scoring
import drillcluster

VERSION_MAJOR=2
VERSION_MINOR=0

RANDOM_SEARCH = 1
EXHAUSTIVE_SEARCH = 2
FROM_FILE = 3
config.AutoSearchType = RANDOM_SEARCH
config.RandomSearchExhaustiveJobs = 2
config.PlacementFile = None

# This is a handle to a GUI front end, if any, else None for command-line usage
GUI = None

def writeGerberHeader22degrees(fid):
    fid.write( \
  """G75*
  G70*
  %OFA0B0*%
  %FSLAX25Y25*%
  %IPPOS*%
  %LPD*%
  %AMOC8*
  5,1,8,0,0,1.08239X$1,22.5*
  %
  """)

def writeGerberHeader0degrees(fid):
    fid.write( \
  """G75*
  G70*
  %OFA0B0*%
  %FSLAX25Y25*%
  %IPPOS*%
  %LPD*%
  %AMOC8*
  5,1,8,0,0,1.08239X$1,0.0*
  %
  """)

writeGerberHeader = writeGerberHeader22degrees

def writeApertureMacros(fid, usedDict):
    keys = list(config.GAMT.keys())
    keys.sort()
    for key in keys:
        if key in usedDict:
            config.GAMT[key].writeDef(fid)

def writeApertures(fid, usedDict):
    keys = list(config.GAT.keys())
    keys.sort()
    for key in keys:
        if key in usedDict:
            config.GAT[key].writeDef(fid)

def writeGerberFooter(fid):
    fid.write('M02*\n')

def writeExcellonHeader(fid):
    fid.write('%\n')

def writeExcellonFooter(fid):
    fid.write('M30\n')

def writeExcellonTool(fid, tool, size):
    fid.write('%sC%f\n' % (tool, size))

def writeFiducials(fid, drawcode, OriginX, OriginY, MaxXExtent, MaxYExtent):
    """Place fiducials at arbitrary points. The FiducialPoints list in the config specifies
    sets of X,Y co-ordinates. Positive values of X/Y represent offsets from the lower left
    of the panel. Negative values of X/Y represent offsets from the top right. So:
           FiducialPoints = 0.125,0.125,-0.125,-0.125
    means to put a fiducial 0.125,0.125 from the lower left and 0.125,0.125 from the top right"""
    fid.write('%s*\n' % drawcode)    # Choose drawing aperture

    fList = config.Config['fiducialpoints'].split(',')
    for i in range(0, len(fList), 2):
        x,y = float(fList[i]), float(fList[i+1])
        if x>=0:
            x += OriginX
        else:
            x = MaxXExtent + x
        if y>=0:
            y += OriginX
        else:
            y = MaxYExtent + y
        fid.write('X%07dY%07dD03*\n' % (util.in2gerb(x), util.in2gerb(y)))

def writeOutline(fid, OriginX, OriginY, MaxXExtent, MaxYExtent):
    # Write width-1 aperture to file
    AP = aptable.Aperture(aptable.Circle, 'D10', 0.001)
    AP.writeDef(fid)

    # Choose drawing aperture D10
    fid.write('D10*\n')

    # Draw the rectangle
    fid.write('X%07dY%07dD02*\n' % (util.in2gerb(OriginX), util.in2gerb(OriginY)))        # Bottom-left
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX), util.in2gerb(MaxYExtent)))     # Top-left
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent), util.in2gerb(MaxYExtent)))  # Top-right
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent), util.in2gerb(OriginY)))     # Bottom-right
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX), util.in2gerb(OriginY)))        # Bottom-left


def writeCropMarks(fid, drawing_code, OriginX, OriginY, MaxXExtent, MaxYExtent):
    """Add corner crop marks on the given layer"""

    # Draw 125mil lines at each corner, with line edge right up against
    # panel border. This means the center of the line is D/2 offset
    # from the panel border, where D is the drawing line diameter.
    fid.write('%s*\n' % drawing_code)    # Choose drawing aperture

    offset = config.GAT[drawing_code].dimx/2.0

    # Lower-left
    x = OriginX + offset
    y = OriginY + offset
    fid.write('X%07dY%07dD02*\n' % (util.in2gerb(x+0.125), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.125)))

    # Lower-right
    x = MaxXExtent - offset
    y = OriginY + offset
    fid.write('X%07dY%07dD02*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.125)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x-0.125), util.in2gerb(y+0.000)))

    # Upper-right
    x = MaxXExtent - offset
    y = MaxYExtent - offset
    fid.write('X%07dY%07dD02*\n' % (util.in2gerb(x-0.125), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y-0.125)))

    # Upper-left
    x = OriginX + offset
    y = MaxYExtent - offset
    fid.write('X%07dY%07dD02*\n' % (util.in2gerb(x+0.000), util.in2gerb(y-0.125)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.000), util.in2gerb(y+0.000)))
    fid.write('X%07dY%07dD01*\n' % (util.in2gerb(x+0.125), util.in2gerb(y+0.000)))

def disclaimer(ack = False):
    print("""
  ****************************************************
  *           R E A D    C A R E F U L L Y           *
  *                                                  *
  * This program comes with no warranty. You use     *
  * this program at your own risk. Do not submit     *
  * board files for manufacture until you have       *
  * thoroughly inspected the output of this program  *
  * using a previewing program such as:              *
  *                                                  *
  * Windows:                                         *
  *          - GC-Prevue <http://www.graphicode.com> *
  *          - ViewMate  <http://www.pentalogix.com> *
  *                                                  *
  * Linux:                                           *
  *          - gerbv <http://gerbv.sourceforge.net>  *
  *                                                  *
  * By using this program you agree to take full     *
  * responsibility for the correctness of the data   *
  * that is generated by this program.               *
  ****************************************************

  To agree to the above terms, press 'y' then Enter.
  Any other key will exit the program.

  """)
    if ack:
        return
    s = input()
    # Couldn't get `s == "y"` to work, but the following works correctly on python 3.2 on w64
    if s[0] == "y"[0]:
        return

    print("\nExiting...")
    sys.exit(0)

def tile_jobs(Jobs):
    """Take a list of raw Job objects and find best tiling by calling tile_search"""

    # We must take the raw jobs and construct a list of 4-tuples (Xdim,Ydim,job,rjob).
    # This means we must construct a rotated job for each entry. We first sort all
    # jobs from largest to smallest. This should give us the best tilings first so
    # we can interrupt the tiling process and get a decent layout.
    L = []
    sortJobs = schwartz.schwartz(Jobs, jobs.Job.maxdimension)
    sortJobs.reverse()

    for job in sortJobs:
        Xdim = job.width_in()
        Ydim = job.height_in()
        rjob = jobs.rotateJob(job, 90)  ##NOTE: This will only try 90 degree rotations though 180 & 270 are available

        for count in range(job.Repeat):
            L.append( (Xdim,Ydim,job,rjob) )

    PX,PY = config.Config['panelwidth'],config.Config['panelheight']
    if config.AutoSearchType==RANDOM_SEARCH:
        tile = tilesearch2.tile_search2(L, PX, PY)
    else:
        tile = tilesearch1.tile_search1(L, PX, PY)

    if not tile:
        raise RuntimeError('Panel size %.2f"x%.2f" is too small to hold jobs' % (PX,PY))

    return tile

def merge(opts, gui = None):
    writeGerberHeader = writeGerberHeader22degrees

    global GUI
    GUI = gui

    if opts.octagons == 'rotate':
        writeGerberHeader = writeGerberHeader0degrees
    else:
        writeGerberHeader = writeGerberHeader22degrees

    if opts.search == 'random':
        config.AutoSearchType = RANDOM_SEARCH
    else:
        config.AutoSearchType = EXHAUSTIVE_SEARCH
 
    config.RandomSearchExhaustiveJobs = opts.rs_esjobs
    config.SearchTimeout = opts.search_timeout

    if opts.place_file:
        config.AutoSearchType = FROM_FILE
        config.PlacementFile = opts.place_file

    if opts.no_trim_gerber:
        config.TrimGerber = 0
    if opts.no_trim_excellon:
        config.TrimExcellon = 0

    config.text = opts.text
    config.text_size = opts.text_size
    config.text_stroke = opts.text_stroke
    config.text_x = opts.text_x
    config.text_y = opts.text_y

    # Load up the Jobs global dictionary, also filling out GAT, the
    # global aperture table and GAMT, the global aperture macro table.
    updateGUI("Reading job files...")
    config.parseConfigFile(opts.configfile)

    # Force all X and Y coordinates positive by adding absolute value of minimum X and Y
    for name, job in config.Jobs.items():
        min_x, min_y = job.mincoordinates()
        shift_x = shift_y = 0
        if min_x < 0: shift_x = abs(min_x)
        if min_y < 0: shift_y = abs(min_y)
        if (shift_x > 0) or (shift_y > 0):
            job.fixcoordinates( shift_x, shift_y )

    # Display job properties
    for job in config.Jobs.values():
        print("Job %s:" % job.name)
        if job.Repeat > 1:
            print("(%d instances)" % job.Repeat)
        else:
            print()
        print("  Extents: (%d,%d)-(%d,%d)" % (job.minx,job.miny,job.maxx,job.maxy))
        print("  Size: %f\" x %f\"" % (job.width_in(), job.height_in()))
        print()

    # Trim drill locations and flash data to board extents
    if config.TrimExcellon:
        updateGUI("Trimming Excellon data...")
        print("Trimming Excellon data to board outlines ...")
        for job in config.Jobs.values():
            job.trimExcellon()

    if config.TrimGerber:
        updateGUI("Trimming Gerber data...")
        print("Trimming Gerber data to board outlines ...")
        for job in config.Jobs.values():
            job.trimGerber()

    # We start origin at (0.1", 0.1") just so we don't get numbers close to 0
    # which could trip up Excellon leading-0 elimination.
    OriginX = OriginY = 0.1

    # Read the layout file and construct the nested list of jobs. If there
    # is no layout file, do auto-layout.
    updateGUI("Performing layout...")
    print("Performing layout ...")
    if opts.layoutfile:
        Layout = parselayout.parseLayoutFile(opts.layoutfile)

        # Do the layout, updating offsets for each component job.
        X = OriginX + config.Config['leftmargin']
        Y = OriginY + config.Config['bottommargin']

        for row in Layout:
            row.setPosition(X, Y)
            Y += row.height_in() + config.Config['yspacing']

        # Construct a canonical placement from the layout
        Place = placement.Placement()
        Place.addFromLayout(Layout)

        del Layout

    elif config.AutoSearchType == FROM_FILE:
        Place = placement.Placement()
        Place.addFromFile(config.PlacementFile, config.Jobs)
    else:
        # Do an automatic layout based on our tiling algorithm.
        tile = tile_jobs(config.Jobs.values())

        Place = placement.Placement()
        Place.addFromTiling(tile, OriginX + config.Config['leftmargin'], OriginY + config.Config['bottommargin'])

    (MaxXExtent,MaxYExtent) = Place.extents()
    MaxXExtent += config.Config['rightmargin']
    MaxYExtent += config.Config['topmargin']

    # Start printing out the Gerbers. In preparation for drawing cut marks
    # and crop marks, make sure we have an aperture to draw with. Use a 10mil line.
    # If we're doing a fabrication drawing, we'll need a 1mil line.
    OutputFiles = []

    try:
        fullname = config.MergeOutputFiles['placement']
    except KeyError:
        fullname = 'merged.placement.txt'
    Place.write(fullname)
    OutputFiles.append(fullname)

    # For cut lines
    AP = aptable.Aperture(aptable.Circle, 'D??', config.Config['cutlinewidth'])
    drawing_code_cut = aptable.findInApertureTable(AP)
    if drawing_code_cut is None:
        drawing_code_cut = aptable.addToApertureTable(AP)

    # For crop marks
    AP = aptable.Aperture(aptable.Circle, 'D??', config.Config['cropmarkwidth'])
    drawing_code_crop = aptable.findInApertureTable(AP)
    if drawing_code_crop is None:
        drawing_code_crop = aptable.addToApertureTable(AP)

    # For fiducials
    drawing_code_fiducial_copper = drawing_code_fiducial_soldermask = None
    if config.Config['fiducialpoints']:
        AP = aptable.Aperture(aptable.Circle, 'D??', config.Config['fiducialcopperdiameter'])
        drawing_code_fiducial_copper = aptable.findInApertureTable(AP)
        if drawing_code_fiducial_copper is None:
            drawing_code_fiducial_copper = aptable.addToApertureTable(AP)
        AP = aptable.Aperture(aptable.Circle, 'D??', config.Config['fiducialmaskdiameter'])
        drawing_code_fiducial_soldermask = aptable.findInApertureTable(AP)
        if drawing_code_fiducial_soldermask is None:
            drawing_code_fiducial_soldermask = aptable.addToApertureTable(AP)

    if config.text:
        text_size_ratio = 0.5 # proportion of Y spacing to use for text (much of this is taken up by, e.g., cutlines)
        if not config.text_size:
            print("Computing text size based on Y spacing...")
        text_size = config.text_size if config.text_size else (config.Config['yspacing'] * 1000.0) * text_size_ratio
        if text_size < config.min_text_size:
            print("Warning: Text size ({0} mils) less than minimum ({1} mils), using minimum.".format(text_size, config.min_text_size))
        text_size = max(text_size, config.min_text_size)
        print("Using text size: {0} mils".format(text_size))

        # by default, set stroke proportional to the size based on the ratio of the minimum stroke to the minimum size
        if not config.text_stroke:
            print("Computing text stroke based on text size...")
        text_stroke = config.text_stroke if config.text_stroke else int((text_size / config.min_text_size) * config.min_text_stroke)
        if text_stroke < config.min_text_stroke:
            print("Warning: Text stroke ({0} mils) less than minimum ({1} mils), using minimum.".format(text_stroke, config.min_text_stroke))
        text_stroke = max(text_stroke, config.min_text_stroke)
        print("Using text stroke: {0} mils".format(text_stroke))

        AP = aptable.Aperture(aptable.Circle, 'D??', text_stroke / 1000.0)
        drawing_code_text = aptable.findInApertureTable(AP)
        if drawing_code_text is None:
            drawing_code_text = aptable.addToApertureTable(AP)

    # For fabrication drawing.
    AP = aptable.Aperture(aptable.Circle, 'D??', 0.001)
    drawing_code1 = aptable.findInApertureTable(AP)
    if drawing_code1 is None:
        drawing_code1 = aptable.addToApertureTable(AP)

    updateGUI("Writing merged files...")
    print("Writing merged output files ...")

    for layername in config.LayerList.keys():
        lname = layername
        if lname[0]=='*':
            lname = lname[1:]

        try:
            fullname = config.MergeOutputFiles[layername]
        except KeyError:
            fullname = 'merged.%s.ger' % lname
        OutputFiles.append(fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Determine which apertures and macros are truly needed
        apUsedDict = {}
        apmUsedDict = {}
        for job in Place.jobs:
            apd, apmd = job.aperturesAndMacros(layername)
            apUsedDict.update(apd)
            apmUsedDict.update(apmd)

        # Increase aperature sizes to match minimum feature dimension
        if layername in config.MinimumFeatureDimension:

            print("  Thickening", lname, "feature dimensions ...")

            # Fix each aperture used in this layer
            for ap in list(apUsedDict.keys()):
                new = config.GAT[ap].getAdjusted( config.MinimumFeatureDimension[layername] )
                if not new: ## current aperture size met minimum requirement
                    continue
                else:       ## new aperture was created
                    new_code = aptable.findOrAddAperture(new) ## get name of existing aperture or create new one if needed
                    del apUsedDict[ap]                        ## the old aperture is no longer used in this layer
                    apUsedDict[new_code] = None               ## the new aperture will be used in this layer

                    # Replace all references to the old aperture with the new one
                    for joblayout in Place.jobs:
                        job = joblayout.job ##access job inside job layout
                        temp = []
                        if job.hasLayer(layername):
                            for x in job.commands[layername]:
                                if x == ap:
                                    temp.append(new_code) ## replace old aperture with new one
                                else:
                                    temp.append(x)        ## keep old command
                            job.commands[layername] = temp

        if config.Config['cutlinelayers'] and (layername in config.Config['cutlinelayers']):
            apUsedDict[drawing_code_cut]=None

        if config.Config['cropmarklayers'] and (layername in config.Config['cropmarklayers']):
            apUsedDict[drawing_code_crop]=None

        if config.Config['fiducialpoints']:
            if ((layername=='*toplayer') or (layername=='*bottomlayer')):
                apUsedDict[drawing_code_fiducial_copper] = None
            elif ((layername=='*topsoldermask') or (layername=='*bottomsoldermask')):
                apUsedDict[drawing_code_fiducial_soldermask] = None

        if config.text:
            apUsedDict[drawing_code_text] = None

        # Write only necessary macro and aperture definitions to Gerber file
        writeApertureMacros(fid, apmUsedDict)
        writeApertures(fid, apUsedDict)

        # Finally, write actual flash data
        for job in Place.jobs:

            updateGUI("Writing merged output files...")
            job.writeGerber(fid, layername)

            if config.Config['cutlinelayers'] and (layername in config.Config['cutlinelayers']):
                fid.write('%s*\n' % drawing_code_cut)    # Choose drawing aperture
                job.writeCutLines(fid, drawing_code_cut, OriginX, OriginY, MaxXExtent, MaxYExtent)

        if config.Config['cropmarklayers']:
            if layername in config.Config['cropmarklayers']:
                writeCropMarks(fid, drawing_code_crop, OriginX, OriginY, MaxXExtent, MaxYExtent)

        if config.Config['fiducialpoints']:
            if ((layername=='*toplayer') or (layername=='*bottomlayer')):
                writeFiducials(fid, drawing_code_fiducial_copper, OriginX, OriginY, MaxXExtent, MaxYExtent)
            elif ((layername=='*topsoldermask') or (layername=='*bottomsoldermask')):
                writeFiducials(fid, drawing_code_fiducial_soldermask, OriginX, OriginY, MaxXExtent, MaxYExtent)
        if config.Config['outlinelayers'] and (layername in config.Config['outlinelayers']):
            writeOutline(fid, OriginX, OriginY, MaxXExtent, MaxYExtent)

        if config.text:
            Y += row.height_in() + config.Config['yspacing']
            x = config.text_x if config.text_x else util.in2mil(OriginX + config.Config['leftmargin'])  + 100 # convert inches to mils 100 is extra margin
            y_offset = ((config.Config['yspacing'] * 1000.0) - text_size) / 2.0
            y = config.text_y if config.text_y else util.in2mil(OriginY + config.Config['bottommargin'] + Place.jobs[0].height_in()) + y_offset # convert inches to mils
            fid.write('%s*\n' % drawing_code_text)    # Choose drawing aperture
            makestroke.writeString(fid, config.text, int(util.mil2gerb(x)), int(util.mil2gerb(y)), 0, int(text_size))
        writeGerberFooter(fid)

        fid.close()

    # Write board outline layer if selected
    fullname = config.Config['outlinelayerfile']
    if fullname and fullname.lower() != "none":
        OutputFiles.append(fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Write width-1 aperture to file
        AP = aptable.Aperture(aptable.Circle, 'D10', 0.001)
        AP.writeDef(fid)

        # Choose drawing aperture D10
        fid.write('D10*\n')

        # Draw the rectangle
        fid.write('X%07dY%07dD02*\n' % (util.in2gerb(OriginX), util.in2gerb(OriginY)))        # Bottom-left
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX), util.in2gerb(MaxYExtent)))     # Top-left
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent), util.in2gerb(MaxYExtent)))  # Top-right
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(MaxXExtent), util.in2gerb(OriginY)))     # Bottom-right
        fid.write('X%07dY%07dD01*\n' % (util.in2gerb(OriginX), util.in2gerb(OriginY)))        # Bottom-left

        writeGerberFooter(fid)
        fid.close()

    # Write scoring layer if selected
    fullname = config.Config['scoringfile']
    if fullname and fullname.lower() != "none":
        OutputFiles.append(fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)

        # Write width-1 aperture to file
        AP = aptable.Aperture(aptable.Circle, 'D10', 0.001)
        AP.writeDef(fid)

        # Choose drawing aperture D10
        fid.write('D10*\n')

        # Draw the scoring lines
        scoring.writeScoring(fid, Place, OriginX, OriginY, MaxXExtent, MaxYExtent)

        writeGerberFooter(fid)
        fid.close()

    # Get a list of all tools used by merging keys from each job's dictionary
    # of tools.
    toolNum = 0

    # First construct global mapping of diameters to tool numbers
    for job in config.Jobs.values():
        for tool,diam in job.xdiam.items():
            if diam in config.GlobalToolRMap:
                continue

            toolNum += 1
            config.GlobalToolRMap[diam] = "T%02d" % toolNum

    # Cluster similar tool sizes to reduce number of drills
    if config.Config['drillclustertolerance'] > 0:
        config.GlobalToolRMap = drillcluster.cluster( config.GlobalToolRMap, config.Config['drillclustertolerance'] )
        drillcluster.remap( Place.jobs, list(config.GlobalToolRMap.items()) )

    # Now construct mapping of tool numbers to diameters
    for diam,tool in config.GlobalToolRMap.items():
        config.GlobalToolMap[tool] = diam

    # Tools is just a list of tool names
    Tools = list(config.GlobalToolMap.keys())
    Tools.sort()

    fullname = config.Config['fabricationdrawingfile']
    if fullname and fullname.lower() != 'none':
        if len(Tools) > strokes.MaxNumDrillTools:
            raise RuntimeError("Only %d different tool sizes supported for fabrication drawing." % strokes.MaxNumDrillTools)

        OutputFiles.append(fullname)
        fid = open(fullname, 'wt')
        writeGerberHeader(fid)
        writeApertures(fid, {drawing_code1: None})
        fid.write('%s*\n' % drawing_code1)    # Choose drawing aperture

        fabdrawing.writeFabDrawing(fid, Place, Tools, OriginX, OriginY, MaxXExtent, MaxYExtent)

        writeGerberFooter(fid)
        fid.close()

    # Finally, print out the Excellon
    try:
        fullname = config.MergeOutputFiles['drills']
    except KeyError:
        fullname = 'merged.drills.xln'
    OutputFiles.append(fullname)
    fid = open(fullname, 'wt')

    writeExcellonHeader(fid)

    # Ensure each one of our tools is represented in the tool list specified
    # by the user.
    for tool in Tools:
        try:
            size = config.GlobalToolMap[tool]
        except:
            raise RuntimeError("INTERNAL ERROR: Tool code %s not found in global tool map" % tool)

        writeExcellonTool(fid, tool, size)

        #for row in Layout:
        #  row.writeExcellon(fid, size)
        for job in Place.jobs:
            job.writeExcellon(fid, size)

    writeExcellonFooter(fid)
    fid.close()

    updateGUI("Closing files...")

    # Compute stats
    jobarea = 0.0
    for job in Place.jobs:
        jobarea += job.jobarea()

    totalarea = ((MaxXExtent-OriginX)*(MaxYExtent-OriginY))

    ToolStats = {}
    drillhits = 0
    for tool in Tools:
        ToolStats[tool]=0
        for job in Place.jobs:
            hits = job.drillhits(config.GlobalToolMap[tool])
            ToolStats[tool] += hits
            drillhits += hits

    try:
        fullname = config.MergeOutputFiles['toollist']
    except KeyError:
        fullname = 'merged.toollist.drl'
    OutputFiles.append(fullname)
    fid = open(fullname, 'wt')

    print('-'*50)
    print("     Job Size : %f\" x %f\"" % (MaxXExtent-OriginX, MaxYExtent-OriginY))
    print("     Job Area : %.2f sq. in." % totalarea)
    print("   Area Usage : %.1f%%" % (jobarea/totalarea*100))
    print("   Drill hits : %d" % drillhits)
    print("Drill density : %.1f hits/sq.in." % (drillhits/totalarea))

    print("\nTool List:")
    smallestDrill = 999.9
    for tool in Tools:
        if ToolStats[tool]:
            fid.write('%s %.4fin\n' % (tool, config.GlobalToolMap[tool]))
            print("  %s %.4f\" %5d hits" % (tool, config.GlobalToolMap[tool], ToolStats[tool]))
            smallestDrill = min(smallestDrill, config.GlobalToolMap[tool])

    fid.close()
    print("Smallest Tool: %.4fin" % smallestDrill)

    print()
    print("Output Files :")
    for f in OutputFiles:
        print("  ", f)

    if (MaxXExtent-OriginX)>config.Config['panelwidth'] or (MaxYExtent-OriginY)>config.Config['panelheight']:
        print('*'*75)
        print("*")
        print("* ERROR: Merged job %.3f\"x%.3f\" exceeds panel dimensions of %.3f\"x%.3f\"" % (MaxXExtent-OriginX, MaxYExtent-OriginY, config.Config['panelwidth'],config.Config['panelheight']))
        print("*")
        print('*'*75)
        sys.exit(1)

    # Done!
    return 0

def updateGUI(text = None):
    global GUI
    if GUI != None:
        GUI.updateProgress(text)

if __name__=="__main__":
    parser = argparse.ArgumentParser(description="Merge gerber files for individual boards into a single panel. Can follow\nmanual layouts or search for optimal arrangements.", epilog="If a layout file is not specified, automatic placement is performed. If the\nplacement is read from a file, then no automatic placement is performed and\nthe layout file (if any) is ignored.\n\nNOTE: The dimensions of each job are determined solely by the maximum extent\nof the board outline layer for each job.", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--search', choices=['random', 'exhaustive'], default='random', help="Specify search method for automatic layouts. Defaults to random.")
    parser.add_argument('--place-file', type=argparse.FileType('r'), help="Specify a place file (output of previous searches)")
    parser.add_argument('--version', action='version', version="%(prog)s "+str(VERSION_MAJOR)+"."+str(VERSION_MINOR))
    parser.add_argument('--rs-esjobs', type=int, help="When using random search, exhaustively search N jobs for each random placement. Only matters when using random search. Defaults to 2.", metavar='N', default=2)
    parser.add_argument('--search-timeout', type=int, help="When using random search, search for T seconds for best random placement. Without this option the search will continue until interrupted by user.", metavar='T', default=0)
    parser.add_argument('--no-trim-gerber', action='store_true', help="Do not attempt to trim Gerber data to extents of board")
    parser.add_argument('--no-trim-excellon', action='store_true', help="Do not attempt to trim Excellon  data to extents of board")
    parser.add_argument('--octagons', choices=['rotate', 'normal'], default='normal', help="Generate octagons in two different styles depending on the argument. 'rotate' sets rotation to 0 while 'normal' rotates the octagons 22.5deg")
    parser.add_argument('--ack', action='store_true', help="Automatically acknowledge disclaimer/warning")
    parser.add_argument('--text', type=str, help="A string of text to print between boards in layout")
    parser.add_argument('--text-size', type=int, metavar='N', help="Size (height in mils) of text. Should be less than 'y spacing' set in .cfg file")
    parser.add_argument('--text-stroke', type=int, metavar='N', default=10, help="Stroke (width in mils) of text.")
    parser.add_argument('--text-x', type=int, default=0, metavar='X', help="X position of text. Defaults to inside space between jobs")
    parser.add_argument('--text-y', type=int, default=0, metavar='Y', help="Y position of text. Defaults to inside space between jobs")
    parser.add_argument('configfile', type=argparse.FileType('r'), help=".cfg file setting configuration values for this panel")
    parser.add_argument('layoutfile', type=argparse.FileType('r'), default=None, nargs='?', help=".xml file specifying a manual layout for this panel")
    
    args = parser.parse_args()

    # Display the disclaimer, skipping it if specified
    disclaimer(args.ack)

    # Run gerbmerge
    sys.exit(merge(args))
# vim: expandtab ts=2 sw=2 ai syntax=python
