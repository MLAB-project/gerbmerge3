#!/usr/bin/env python
"""
Parse the job layout specification file.

Requires:

  - SimpleParse 2.1 or higher
              http://simpleparse.sourceforge.net


--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""
import sys
import string

import xml.etree.ElementTree as ET

import config
import jobs

class Panel:                 # Meant to be subclassed as either a Row() or Col()
  def __init__(self):
    self.x = None
    self.y = None
    self.jobs = []           # List (left-to-right or bottom-to-top) of JobLayout() or Row()/Col() objects

  def canonicalize(self):    # Return plain list of JobLayout objects at the roots of all trees
    L = []
    for job in self.jobs:
      L = L + job.canonicalize()
    return L

  def addjob(self, job):     # Either a JobLayout class or Panel (sub)class
    assert isinstance(job, Panel) or isinstance(job, jobs.JobLayout)
    self.jobs.append(job)

  def addwidths(self):
    "Return width in inches"
    width = 0.0
    for job in self.jobs:
      width += job.width_in() + config.Config['xspacing']
    width -= config.Config['xspacing']
    return width

  def maxwidths(self):
    "Return maximum width in inches of any one subpanel"
    width = 0.0
    for job in self.jobs:
      width = max(width,job.width_in())
    return width

  def addheights(self):
    "Return height in inches"
    height = 0.0
    for job in self.jobs:
      height += job.height_in() + config.Config['yspacing']
    height -= config.Config['yspacing']
    return height

  def maxheights(self):
    "Return maximum height in inches of any one subpanel"
    height = 0.0
    for job in self.jobs:
      height = max(height,job.height_in())
    return height

  def writeGerber(self, fid, layername):
    for job in self.jobs:
      job.writeGerber(fid, layername)

  def writeExcellon(self, fid, tool):
    for job in self.jobs:
      job.writeExcellon(fid, tool)

  def writeDrillHits(self, fid, tool, toolNum):
    for job in self.jobs:
      job.writeDrillHits(fid, tool, toolNum)

  def writeCutLines(self, fid, drawing_code, X1, Y1, X2, Y2):
    for job in self.jobs:
      job.writeCutLines(fid, drawing_code, X1, Y1, X2, Y2)

  def drillhits(self, tool):
    hits = 0
    for job in self.jobs:
      hits += job.drillhits(tool)

    return hits

  def jobarea(self):
    area = 0.0
    for job in self.jobs:
      area += job.jobarea()

    return area

class Row(Panel):
  def __init__(self):
    Panel.__init__(self)
    self.LR = 1   # Horizontal arrangement

  def width_in(self):
    return self.addwidths()

  def height_in(self):
    return self.maxheights()

  def setPosition(self, x, y):   # In inches
    self.x = x
    self.y = y
    for job in self.jobs:
      job.setPosition(x,y)
      x += job.width_in() + config.Config['xspacing']

class Col(Panel):
  def __init__(self):
    Panel.__init__(self)
    self.LR = 0   # Vertical arrangement

  def width_in(self):
    return self.maxwidths()

  def height_in(self):
    return self.addheights()

  def setPosition(self, x, y):   # In inches
    self.x = x
    self.y = y
    for job in self.jobs:
      job.setPosition(x,y)
      y += job.height_in() + config.Config['yspacing']

def canonicalizePanel(panel):
  L = []
  for job in panel:
    L = L + job.canonicalize()
  return L

def findJob(jobname, rotated, Jobs=config.Jobs):
  """
    Find a job in config.Jobs, possibly rotating it
    If job not in config.Jobs add it for future reference
    Return found job
  """

  if rotated == 90:
    fullname = jobname + '*rotated90'
  elif rotated == 180:
    fullname = jobname + '*rotated180'
  elif rotated == 270:
    fullname = jobname + '*rotated270'
  else:
    fullname = jobname

  try:
    for existingjob in Jobs.keys():
      if existingjob.lower() == fullname.lower(): ## job names are case insensitive
        job = Jobs[existingjob]
        return jobs.JobLayout(job)
  except:
    pass

  # Perhaps we just don't have a rotated job yet
  if rotated:
    try:
      for existingjob in Jobs.keys():
        if existingjob.lower() == jobname.lower(): ## job names are case insensitive
          job = Jobs[existingjob]
    except:
      raise RuntimeError("Job name '%s' not found" % jobname)
  else:
    raise RuntimeError("Job name '%s' not found" % jobname)

  # Make a rotated job
  job = jobs.rotateJob(job, rotated)
  Jobs[fullname] = job

  return jobs.JobLayout(job)

def parseJobSpec(spec, data):
  rotation = spec.get('rotate', default="0")
  if rotation == "true":
    rotation = 90
  else:
    try:
      rotation = int(rotation)
    except ValueError:
      raise RuntimeError("Rotation must be specified as 'true' or multiples of 90.")

  return findJob(spec.get('name'), rotation)

def parseColSpec(spec):
  jobs = Col()

  for coljob in spec:
    if coljob.tag == 'board':
      pass
      #jobs.addjob(parseJobSpec(coljob))
    elif coljob.tag == 'row':
      jobs.addjob(parseColSpec(coljob))
    else:
      raise RuntimeError("Unexpected element '%s' encountered while parsing jobs file" % coljob.tag)

  return jobs

def parseRowSpec(spec):
  jobs = Row()

  for rowjob in spec:
    if rowjob.tag == 'board':
      pass
      #jobs.addjob(parseJobSpec(rowjob))
    elif rowjob.tag == 'col':
      jobs.addjob(parseColSpec(rowjob))
    else:
      raise RuntimeError("Unexpected element '%s' encountered while parsing jobs file" % rowjob.tag)

  return jobs

def parseLayoutFile(fname):
  """config.Jobs is a dictionary of ('jobname', Job Object).

     The return value is a nested array. The primary dimension
     of the array is one row:

         [ Row1, Row2, Row3 ]

     Each row element consists of a list of jobs or columns (i.e.,
     JobLayout or Col objects).

     Each column consists of a list of either jobs or rows.
     These are recursive, so it can look like:

        [
          Row([JobLayout(), Col([ Row([JobLayout(), JobLayout()]),
                                     JobLayout()       ]),         JobLayout() ]),   # That was row 0
          Row([JobLayout(), JobLayout()])                                            # That was row 1
        ]

     This is a panel with two rows. In the first row there is
     a job, a column, and another job, from left to right. In the
     second row there are two jobs, from left to right.

     The column in the first row has two jobs side by side, then
     another one above them.
  """

  try:
    file = open(fname, 'rt')
  except Exception as detail:
    raise RuntimeError("Unable to open layout file: %s\n  %s" % (fname, str(detail)))

  # Preprocess the XML jobs file removing lines that start with '#' as those're comment lines.
  # They're not handled by the XML parser, so we remove them beforehand.
  unparsedXml = ""
  for line in file:
    if line[0] != '#':
      unparsedXml += line

  # Attempt to parse the jobs file
  try:
    root = ET.fromstring(unparsedXml)
  except ET.ParseError as e:
    raise RuntimeError("Layout file cannot be parsed. Error at %d, %d." % e.position)

  # Build up the array of rows
  Rows = []
  for rowspec in root.findall('row'):
    Rows.append(parseRowSpec(rowspec))

  return Rows

if __name__=="__main__":
    file = open(sys.argv[1])
    unparsedXml = ""
    for line in file:
        if line[0] != '#':
            unparsedXml += line

    xml = ET.fromstring(unparsedXml)
    ET.dump(xml)
