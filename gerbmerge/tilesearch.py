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
from math import factorial

import tiling

class TileSearch:
    def __init__(self, jobs, x, y, xspacing, yspacing, exhaustiveSearchJobs, searchTimeout):
        # Start the start-time counter. Since this is in Init() and not in *Search(),
        # it will be a little off, but that shouldn't be a problem.
        self.startTime = time.time()

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
        
        # Track the number of permutations checked so far
        self.permutations = 0
        
        # Track the possible permutations given the `jobs` provided
        # There are (2**N)*(N!) possible permutations where N is the number of jobs.
        # This is assuming all jobs are unique and each job has a rotation (i.e., is not
        # square). Practically, these assumptions make no difference because the software
        # currently doesn't optimize for cases of repeated jobs.
        self.possiblePermutations = (2**len(jobs))*factorial(len(jobs))

        # Store the total list of jobs to place
        self.jobs = jobs

        # Store the x/y spacing configured for this tiling
        self.xspacing = xspacing
        self.yspacing = yspacing

        # Store the X and Y grid of the Tiling
        # We also store a blank tiling to start
        self.baseTiling = tiling.Tiling(x, y, self.xspacing, self.yspacing)

        # Store some other configuration values
        self.RandomSearchExhaustiveJobs = exhaustiveSearchJobs
        self.SearchTimeout = searchTimeout

    def __str__(self):
        if self.bestTiling:
            area = self.bestTiling.area()
            utilization = self.bestTiling.usedArea() / area * 100.0
        else:
            area = float("inf")
            utilization = 0.0

        if self.placements > 0:
            return "\n  %ld placements | Smallest area: %.1f sq. in. | Best utilization: %.1f%%" % (self.placements, area, utilization)
        elif self.permutations > 0:
            percent = 100.0 * self.permutations / self.possiblePermutations
            return "\n  %5.2f complete | %d/%d Permutations checked | Smallest area: %.1f sq. in. / Best utilization: %.1f%%" % (percent, self.permutations, self.possiblePermutations, area, utilization)
        else:
            return "\n  No calculations yet."

    def RandomSearch(self):
        """Perform a random search through all possible jobs given the provided panel size.
        Only self.placements & lastCheckTime are modified within this method.
        """
        r = random.Random()
        N = len(self.jobs)

        # M is the number of jobs that will be placed randomly.
        # N-M is the number of jobs that will be searched exhaustively.
        M = N - self.RandomSearchExhaustiveJobs
        M = max(M,0)

        # Must escape with Ctrl-C
        while 1:
            currentTiling = self.baseTiling.clone()
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

                    self.ExhaustiveSearch(remainingJobs, currentTiling, True, False)

            self.placements += 1

            # If we've been at this for one period, print some status information
            if time.time() > self.lastCheckTime + self.syncPeriod:
                self.lastCheckTime = time.time()
                print(self)

                # Check for timeout
                if (self.SearchTimeout > 0) and ((time.time() - self.startTime) > self.SearchTimeout):
                    raise KeyboardInterrupt


    def ExhaustiveSearch(self, Jobs, TSoFar, firstAddPoint, printStats=True):
        """This recursive function does the following with an existing tiling TSoFar:

           * For each 4-tuple (Xdim,Ydim,job,rjob) in Jobs, the non-rotated 'job' is selected

           * For the non-rotated job, the list of valid add-points is found

           * For each valid add-point, the job is placed at this point in a new,
             cloned tiling.

           * The function then calls its recursively with the remaining list of
             jobs.

           * The rotated job is then selected and the list of valid add-points is
             found. Again, for each valid add-point the job is placed there in
             a new, cloned tiling.

           * Once again, the function calls itself recursively with the remaining
             list of jobs.

           * The best tiling encountered from all recursive calls is returned.

           If TSoFar is None it means this combination of jobs is not tileable.

           The side-effect of this function is to set _TBestTiling and _TBestScore
           to the best tiling encountered so far. _TBestTiling could be None if
           no valid tilings have been found so far.
        """

        if not TSoFar:
            return (None, float("inf"))

        if not Jobs:
            # Update the best tiling and score. If the new tiling matches
            # the best score so far, compare on number of corners, trying to
            # minimize them.
            score = TSoFar.area()

            if score < self.bestScore or (score == self.bestScore and TSoFar.corners() < self.bestTiling.corners()):
                self.bestTiling = TSoFar
                self.bestScore = score

            if firstAddPoint:
                self.permutations += 1
            return

        minInletSize = tiling.minDimension(Jobs)
        TSoFar.removeInlets(minInletSize)

        for job_ix in range(len(Jobs)):
            # Pop off the next job and construct remaining_jobs, a sub-list
            # of Jobs with the job we've just popped off excluded.
            Xdim,Ydim,job,rjob = Jobs[job_ix]
            remaining_jobs = Jobs[:job_ix]+Jobs[job_ix+1:]

            # Construct add-points for the non-rotated and rotated job.
            # As an optimization, do not construct add-points for the rotated
            # job if the job is a square (duh).
            addpoints1 = TSoFar.validAddPoints(Xdim+self.xspacing,Ydim+self.yspacing)     # unrotated job
            if Xdim != Ydim:
                addpoints2 = TSoFar.validAddPoints(Ydim+self.xspacing,Xdim+self.yspacing)   # rotated job
            else:
                addpoints2 = []

            # Recursively construct tilings for the non-rotated job and
            # update the best-tiling-so-far as we do so.
            if addpoints1:
                for ix in addpoints1:
                    # Clone the tiling we're starting with and add the job at this
                    # add-point.
                    T = TSoFar.clone()
                    T.addJob(ix, Xdim+self.xspacing, Ydim+self.yspacing, job)

                    # Recursive call with the remaining jobs and this new tiling. The
                    # point behind the last parameter is simply so that self.permutations is
                    # only updated once for each permutation, not once per add-point.
                    # A permutation is some ordering of jobs (N! choices) and some
                    # ordering of non-rotated and rotated within that ordering (2**N
                    # possibilities per ordering).
                    self.ExhaustiveSearch(remaining_jobs, T, firstAddPoint and ix==addpoints1[0])
            elif firstAddPoint:
                # Premature prune due to not being able to put this job anywhere. We
                # have pruned off 2^M permutations where M is the length of the remaining
                # jobs.
                self.permutations += 2**len(remaining_jobs)

            if addpoints2:
                for ix in addpoints2:
                    # Clone the tiling we're starting with and add the job at this
                    # add-point. Remember that the job is rotated so swap X and Y
                    # dimensions.
                    T = TSoFar.clone()
                    T.addJob(ix, Ydim+self.xspacing, Xdim+self.yspacing, rjob)

                    # Recursive call with the remaining jobs and this new tiling.
                    self.ExhaustiveSearch(remaining_jobs, T, firstAddPoint and ix==addpoints2[0])
            elif firstAddPoint:
                # Premature prune due to not being able to put this job anywhere. We
                # have pruned off 2^M permutations where M is the length of the remaining
                # jobs.
                self.permutations += 2**len(remaining_jobs)

            # If we've been at this for one period, print some status information
            if printStats and time.time() > self.lastCheckTime + self.syncPeriod:
                self.lastCheckTime = time.time()
                print(self)

                # Check for timeout
                if (self.SearchTimeout > 0) and ((time.time() - self.startTime) > self.SearchTimeout):
                    raise KeyboardInterrupt

def tile_search2(Jobs, X, Y, xspacing, yspacing, exhaustiveSearchJobs, searchTimeout):
    """Wrapper around _tile_search2 to handle keyboard interrupt, etc."""

    print("="*70)
    print("Starting random placement trials. You must press Ctrl-C to")
    print("stop the process and use the best placement so far.")
    print("Estimated maximum possible utilization is %.1f%%." % (tiling.maxUtilization(Jobs,xspacing,yspacing)*100))

    try:
        x = TileSearch(Jobs, X, Y, xspacing, yspacing, exhaustiveSearchJobs, searchTimeout)
        x.RandomSearch()
    except KeyboardInterrupt:
        print(x)
        print("\nInterrupted.")

    computeTime = time.time() - x.startTime
    print("Computed %ld placements in %d seconds / %.1f placements/second" % (x.placements, computeTime, x.placements/computeTime))
    print("="*70)

    return x.bestTiling

def tile_search1(Jobs, X, Y, xspacing, yspacing, searchTimeout):
    """Wrapper around _tile_search1 to handle keyboard interrupt, etc."""
    
    x = TileSearch(Jobs, X, Y, xspacing, yspacing, 0, searchTimeout)

    print('='*70)
    print("Starting placement using exhaustive search.")
    print("There are %ld possible permutations..." % x.possiblePermutations)
    if x.possiblePermutations < 1e4:
        print("this'll take no time at all.")
    elif x.possiblePermutations < 1e5:
        print("surf the web for a few minutes.")
    elif x.possiblePermutations < 1e6:
        print("take a long lunch.")
    elif x.possiblePermutations < 1e7:
        print("come back tomorrow.")
    else:
        print("don't hold your breath.")
    print("Press Ctrl-C to stop and use the best placement so far.")
    print("Estimated maximum possible utilization is %.1f%%." % (tiling.maxUtilization(Jobs,xspacing,yspacing)*100))

    try:
        x.ExhaustiveSearch(Jobs, tiling.Tiling(X,Y,xspacing,yspacing), True)
        print()
    except KeyboardInterrupt:
        print(x)
        print()
        print("Interrupted.")

    computeTime = time.time() - x.startTime
    print("Computed %ld permutations in %d seconds / %.1f permutations/second" % (x.permutations, computeTime, x.permutations/computeTime))
    print('='*70)

    return x.bestTiling