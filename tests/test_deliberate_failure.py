"""Lab 4 Task 2: DELIBERATE failure for the failure demo. Reverted right after.

Pushing this must stop the run in pre_build (the phase that owns tests),
reach no SageMaker training/registration, and fire northstar-ci-build-failure.
"""


def test_deliberate_failure_for_demo():
    assert 1 + 1 == 3, "Deliberate failure (Lab 4 failure demo) - this commit is reverted next"
