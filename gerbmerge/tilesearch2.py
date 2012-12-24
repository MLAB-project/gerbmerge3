#!/usr/bin/env python
"""Tile search using random placement and evaluation. Works surprisingly well.
--------------------------------------------------------------------

This program is licensed under the GNU General Public License (GPL)
Version 3.  See http://www.fsf.org for details of the license.

Rugged Circuits LLC
http://ruggedcircuits.com/gerbmerge
"""

import sys
import time
import random

import config
import tiling
import tilesearch1

import gerbmerge

class TileSearch:
    def __init__(self, jobs, x, y, cfg=config):
        # Track the last time a synchronization occured
        self.lastCheckTime = 0

        # Determine how often this process should synchronize
        # Each process is slightly offset at random to prevent
        # contention.
        self.syncPeriod = 3 + (random.random() - 0.5) / 5

        # Track the best tiling found so far.
        self.bestTiling = None

        # Track the best score found so far. We start with a maximally large
        # value as lower are better
        # This gets synchronized with the global best every `syncPeriod`
        self.bestScore = float("inf")

        # Track how many placements have been attempted
        # This is only tracked per this process
        self.placements = 0

        # Store the total list of jobs to place
        self.jobs = jobs

        # Store the X and Y grid of the Tiling
        # We also store a blank tiling to start
        self.x = x
        self.y = y
        self.tiling = None

        # Store the x/y spacing configured for this tiling
        self.xspacing = cfg.Config['xspacing']
        self.yspacing = cfg.Config['yspacing']

        # Store some other configuration values
        self.RandomSearchExhaustiveJobs = cfg.RandomSearchExhaustiveJobs
        self.SearchTimeout = cfg.SearchTimeout

    def __str__(self):
        if self.bestTiling:
            area = self.bestTiling.area()
            utilization = self.bestTiling.usedArea() / area * 100.0
        else:
            area = float("inf")
            utilization = 0.0

        return "\r  %ld placements / Smallest area: %.1f sq. in. / Best utilization: %.1f%%" % (self.placements, area, utilization)

    def run(self):
        self.startTime = time.time()
        self.lastCheckTime = time.time()
        r = random.Random()
        N = len(self.jobs)

        # M is the number of jobs that will be placed randomly.
        # N-M is the number of jobs that will be searched exhaustively.
        M = N - self.RandomSearchExhaustiveJobs
        M = max(M,0)

        # Must escape with Ctrl-C
        while 1:
            currentTiling = tiling.Tiling(self.x, self.y)
            joborder = r.sample(range(N), N)

            minInletSize = tiling.minDimension(self.jobs)

            for ix in joborder[:M]:
                Xdim,Ydim,job,rjob = self.jobs[ix]

                currentTiling.removeInlets(minInletSize)

                if r.choice([0,1]):
                    addpoints = currentTiling.validAddPoints(Xdim+self.xspacing, Ydim+self.yspacing)
                    if not addpoints:
                        break

                    pt = r.choice(addpoints)
                    currentTiling.addJob(pt, Xdim+self.xspacing, Ydim+self.yspacing, job)
                else:
                    addpoints = currentTiling.validAddPoints(Ydim+self.xspacing, Xdim+self.yspacing)
                    if not addpoints:
                        break

                    pt = r.choice(addpoints)
                    currentTiling.addJob(pt, Ydim+self.xspacing, Xdim+self.yspacing, rjob)
            else:
                # Do exhaustive search on remaining jobs
                if N-M:
                    remainingJobs = []
                    for ix in joborder[M:]:
                        remainingJobs.append(self.jobs[ix])

                    tilesearch1.initialize(0)
                    tilesearch1._tile_search1(remainingJobs, currentTiling, 1)
                    newTiling = tilesearch1.bestTiling()

                    if newTiling:
                        score = newTiling.area()
                    else:
                        score = float("inf")

                    if score < self.bestScore or (score == self.bestScore and newTiling.corners() < self.bestTiling.corners()):
                        self.bestTiling = newTiling
                        self.bestScore = score

            self.placements += 1

            # If we've been at this for one period, print some status information
            if time.time() > self.lastCheckTime + self.syncPeriod:
                self.lastCheckTime = time.time()
                print(self)

                # Check for timeout
                if (self.SearchTimeout > 0) and ((time.time() - self.startTime) > self.SearchTimeout):
                    raise KeyboardInterrupt

        # end while 1

def tile_search2(Jobs, X, Y):
    """Wrapper around _tile_search2 to handle keyboard interrupt, etc."""

    print("="*70)
    print("Starting random placement trials. You must press Ctrl-C to")
    print("stop the process and use the best placement so far.")
    print("Estimated maximum possible utilization is %.1f%%." % (tiling.maxUtilization(Jobs)*100))

    try:
        x = TileSearch(Jobs, X, Y)
        x.run()
    except KeyboardInterrupt:
        print(x)
        print("\nInterrupted.")

    computeTime = time.time() - x.startTime
    print("Computed %ld placements in %d seconds / %.1f placements/second" % (x.placements, computeTime, x.placements/computeTime))
    print("="*70)

    return x.bestTiling
