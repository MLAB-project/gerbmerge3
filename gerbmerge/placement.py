#!/usr/bin/env python
"""A placement is a final arrangement of jobs at given (X,Y) positions.
This class is intended to "un-pack" an arragement of jobs constructed
manually through Layout/Panel/JobLayout/etc. (i.e., a layout.def file)
or automatically through a Tiling. From either source, the result is
simply a list of jobs.
--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""

import sys
import re
from xml.dom.minidom import getDOMImplementation
import xml.etree.ElementTree as ET

import parselayout
import jobs

class Placement:
    def __init__(self):
        self.jobs = []    # A list of JobLayout objects

    def addFromLayout(self, Layout):
        # Layout is a recursive list of JobLayout items. At the end
        # of each tree there is a JobLayout object which has a 'job'
        # member, which is what we're looking for. Fortunately, the
        # canonicalize() function flattens the tree.
        #
        # Positions of jobs have already been set (we're assuming)
        # prior to calling this function.
        self.jobs = self.jobs + parselayout.canonicalizePanel(Layout)

    def addFromTiling(self, T, OriginX, OriginY):
        # T is a Tiling. Calling its canonicalize() method will construct
        # a list of JobLayout objects and set the (X,Y) position of each
        # object.
        self.jobs = self.jobs + T.canonicalize(OriginX,OriginY)

    def extents(self):
        """Return the maximum X and Y value over all jobs"""
        maxX = 0.0
        maxY = 0.0

        for job in self.jobs:
            maxX = max(maxX, job.x+job.width_in())
            maxY = max(maxY, job.y+job.height_in())

        return (maxX,maxY)

    def write(self, fname):
        """Write placement to an XML file of a form similar to that used for the layout files."""
        impl = getDOMImplementation()
        newpanel = impl.createDocument(None, 'panel', None)
        for job in self.jobs:
            board = newpanel.createElement('board')
            splitname = job.job.name.split('*rotated')
            board.setAttribute('name', splitname[0])
            if len(splitname) == 2:
                board.setAttribute('rotate', splitname[1])
            board.setAttribute('x', str(job.x))
            board.setAttribute('y', str(job.y))
            newpanel.documentElement.appendChild(board)
        fid = open(fname, 'wt')
        newpanel.writexml(fid, addindent='\t', newl='\n')
        fid.close()

    def addFromFile(self, file, Jobs):
        """Read placement from a placement XML file, placed against jobs in Jobs list"""
        file = open(file)
        unparsedXml = ""
        for line in file:
            if line[0] != '#':
                unparsedXml += line
        file.close()

        xml = ET.fromstring(unparsedXml)

        for element in xml:
            if element.tag == 'board':
                jobname = element.get('name', None)
                rotate = element.get('rotate', 0)

                try:
                    x = float(element.get('x', 0.0))
                    y = float(element.get('y', 0.0))
                except e:
                    raise RuntimeError("Illegal (x,y) coordinates in placement file:\n %s" % e.line)

                addjob = parselayout.findJob(jobname, rotate, Jobs)
                addjob.setPosition(x,y)
                self.jobs.append(addjob)
