# Kadane's Maximum Subarray

**Proves:** that O(1) space DP is still DP. There is no table --
`current` *is* the entire dynamic-programming state. The region lifter picks up
`best_start`/`best_end` as a span over the array, so the winning subarray is
shaded as it changes.
