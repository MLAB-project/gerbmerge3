import re
import string


def writeheader(fid):
    fid.write('%\n')


def writefooter(fid):
    fid.write('M30\n')


def writetool(fid, tool, size):
    fid.write('%sC%f\n' % (tool, size))


def parseToolList(fname):
    """Parse an Excellon tool list file of the form:
    T01 0.035in
    T02 0.042in
    """
    TL = {}

    try:
        fid = open(fname, 'rt')
    except Exception as detail:
        raise RuntimeError("Unable to open tool list file '%s':\n  %s" % (fname, str(detail)))

    # TODO: Replace following 3 regexes into a single one that checks for in,mm,mil
    pat_in = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*in\s*')
    pat_mm = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*mm\s*')
    pat_mil = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*(?:mil)?')
    for line in fid.xreadlines():
        line = string.strip(line)
        if (not line) or (line[0] in ('#', ';')):
            continue

        # TODO: Change mm/mil to Boolean datatypes
        mm = 0
        mil = 0
        match = pat_in.match(line)
        if not match:
            mm = 1
            match = pat_mm.match(line)
            if not match:
                mil = 1
                match = pat_mil.match(line)
                if not match:
                    continue

        tool, size = match.groups()

        try:
            size = float(size)
        except:
            raise RuntimeError("Tool size in file '%s' is not a valid floating-point number:\n  %s" % (fname, line))

        if mil:
            size = size * 0.001  # Convert mil to inches
        elif mm:
            size = size / 25.4   # Convert mm to inches

        # Canonicalize tool so that T1 becomes T01
        tool = 'T%02d' % int(tool[1:])

        if tool in TL:
            raise RuntimeError("Tool '%s' defined more than once in tool list file '%s'" % (tool, fname))

        TL[tool] = size
    fid.close()

    return TL


def write_excellon(fid, diameter, Xoff, Yoff, leadingZeros, xdiam, xcommands, minx, miny):
    "Write out the data such that the lower-left corner of this job is at the given (X,Y) position, in inches"

    # First convert given inches to 2.4 co-ordinates. Note that Gerber is 2.5 (as of GerbMerge 1.2)
    # and our internal Excellon representation is 2.4 as of GerbMerge
    # version 0.91. We use X,Y to calculate DX,DY in 2.4 units (i.e., with a
    # resolution of 0.0001".
    X = int(round(Xoff / 0.00001))  # First work in 2.5 format to match Gerber
    Y = int(round(Yoff / 0.00001))

    # Now calculate displacement for each position so that we end up at specified origin
    DX = X - minx
    DY = Y - miny

    # Now round down to 2.4 format
    DX = int(round(DX / 10.0))
    DY = int(round(DY / 10.0))

    ltools = []
    for tool, diam in xdiam.items():
        if diam == diameter:
            ltools.append(tool)
    print(ltools)

    if leadingZeros:
        fmtstr = 'X%06dY%06d\n'
    else:
        fmtstr = 'X%dY%d\n'

    # Boogie
    for ltool in ltools:
        if ltool in xcommands:
            for cmd in xcommands[ltool]:
                x, y = cmd
                fid.write(fmtstr % (x + DX, y + DY))
