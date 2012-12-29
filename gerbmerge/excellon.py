import re


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

    pat_in = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*in\s*')
    pat_mm = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*mm\s*')
    pat_mil = re.compile(r'\s*(T\d+)\s+([0-9.]+)\s*(?:mil)?')
    for line in fid.xreadlines():
        line = string.strip(line)
        if (not line) or (line[0] in ('#', ';')):
            continue

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
            size = size*0.001  # Convert mil to inches
        elif mm:
            size = size/25.4   # Convert mm to inches

        # Canonicalize tool so that T1 becomes T01
        tool = 'T%02d' % int(tool[1:])

        if tool in TL:
            raise RuntimeError("Tool '%s' defined more than once in tool list file '%s'" % (tool, fname))

        TL[tool] = size
    fid.close()

    return TL
