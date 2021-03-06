import unittest
import sys
import time
import numpy as np
from openmdao.core.problem import Problem
from openmdao.core.group import Group
from openmdao.core.parallel_group import ParallelGroup
from openmdao.core.component import Component
from openmdao.components.indep_var_comp import IndepVarComp
from openmdao.core.mpi_wrap import MPI, MultiProcFailCheck

from openmdao.test.mpi_util import MPITestCase
from openmdao.recorders import BaseRecorder
from openmdao.test.converge_diverge import ConvergeDiverge
from openmdao.test.example_groups import ExampleGroup

if MPI: # pragma: no cover
    from openmdao.core.petsc_impl import PetscImpl as impl
else:
    from openmdao.core import BasicImpl as impl

class ABCDArrayComp(Component):

    def __init__(self, arr_size=9, delay=0.01):
        super(ABCDArrayComp, self).__init__()
        self.add_param('a', np.ones(arr_size, float))
        self.add_param('b', np.ones(arr_size, float))
        self.add_param('in_string', '')
        self.add_param('in_list', [])

        self.add_output('c', np.ones(arr_size, float))
        self.add_output('d', np.ones(arr_size, float))
        self.add_output('out_string', '')
        self.add_output('out_list', [])

        self.delay = delay

    def solve_nonlinear(self, params, unknowns, resids):
        time.sleep(self.delay)

        unknowns['c'] = params['a'] + params['b']
        unknowns['d'] = params['a'] - params['b']

        unknowns['out_string'] = params['in_string'] + '_' + self.name
        unknowns['out_list']   = params['in_list'] + [1.5]

class RecorderTests(object):
    class Tests(MPITestCase):
        N_PROCS = 2
        recorder = BaseRecorder()
        eps = 1e-5
        t0 = None
        t1 = None

        def run(self, problem):
            self.t0 = time.time()
            problem.run()
            self.t1 = time.time()

        def assertDatasetEquals(self, expected, tolerance):
            self.fail("assertDatasetEquals not implemented!")

        def tearDown(self):
            self.recorder.close()

        def test_basic(self):
            size = 3

            prob = Problem(Group(), impl=impl)

            G1 = prob.root.add('G1', ParallelGroup())
            G1.add('P1', IndepVarComp('x', np.ones(size, float) * 1.0))
            G1.add('P2', IndepVarComp('x', np.ones(size, float) * 2.0))

            prob.root.add('C1', ABCDArrayComp(size))

            prob.root.connect('G1.P1.x', 'C1.a')
            prob.root.connect('G1.P2.x', 'C1.b')
            prob.driver.add_recorder(self.recorder)
            prob.setup(check=False)
            self.run(prob)

            if not MPI or prob.root.comm.rank == 0:

                expected_params = [
                    ("C1.a", [1.0, 1.0, 1.0]),
                    ("C1.b", [2.0, 2.0, 2.0]),
                ]
                expected_unknowns = [
                    ("G1.P1.x", np.array([1.0, 1.0, 1.0])),
                    ("G1.P2.x", np.array([2.0, 2.0, 2.0])),
                    ("C1.c",  np.array([3.0, 3.0, 3.0])),
                    ("C1.d",  np.array([-1.0, -1.0, -1.0])),
                    ("C1.out_string", "_C1"),
                    ("C1.out_list", [1.5]),
                ]
                expected_resids = [
                    ("G1.P1.x", np.array([0.0, 0.0, 0.0])),
                    ("G1.P2.x", np.array([0.0, 0.0, 0.0])),
                    ("C1.c",  np.array([0.0, 0.0, 0.0])),
                    ("C1.d",  np.array([0.0, 0.0, 0.0])),
                    ("C1.out_string", ""),
                    ("C1.out_list", []),
                ]

                expected = (expected_params, expected_unknowns, expected_resids)

                self.assertDatasetEquals(
                    [(['Driver', (1,)], expected)],
                    self.eps
                )

        def test_includes(self):
            size = 3

            prob = Problem(Group(), impl=impl)

            G1 = prob.root.add('G1', ParallelGroup())
            G1.add('P1', IndepVarComp('x', np.ones(size, float) * 1.0))
            G1.add('P2', IndepVarComp('x', np.ones(size, float) * 2.0))

            prob.root.add('C1', ABCDArrayComp(size))

            prob.root.connect('G1.P1.x', 'C1.a')
            prob.root.connect('G1.P2.x', 'C1.b')
            prob.driver.add_recorder(self.recorder)
            self.recorder.options['includes'] = ['C1.*']
            prob.setup(check=False)
            self.run(prob)

            if not MPI or prob.root.comm.rank == 0:
                expected_params = [
                    ("C1.a", [1.0, 1.0, 1.0]),
                    ("C1.b", [2.0, 2.0, 2.0]),
                ]
                expected_unknowns = [
                    ("C1.c",  np.array([3.0, 3.0, 3.0])),
                    ("C1.d",  np.array([-1.0, -1.0, -1.0])),
                    ("C1.out_string", "_C1"),
                    ("C1.out_list", [1.5]),
                ]
                expected_resids = [
                    ("C1.c",  np.array([0.0, 0.0, 0.0])),
                    ("C1.d",  np.array([0.0, 0.0, 0.0])),
                    ("C1.out_string", ""),
                    ("C1.out_list", []),
                ]

                expected = (expected_params, expected_unknowns, expected_resids)

                self.assertDatasetEquals(
                    [(['Driver', (1,)], expected)],
                    self.eps
                )

        def test_includes_and_excludes(self):
            size = 3

            prob = Problem(Group(), impl=impl)

            G1 = prob.root.add('G1', ParallelGroup())
            G1.add('P1', IndepVarComp('x', np.ones(size, float) * 1.0))
            G1.add('P2', IndepVarComp('x', np.ones(size, float) * 2.0))

            prob.root.add('C1', ABCDArrayComp(size))

            prob.root.connect('G1.P1.x', 'C1.a')
            prob.root.connect('G1.P2.x', 'C1.b')
            prob.driver.add_recorder(self.recorder)
            self.recorder.options['includes'] = ['C1.*']
            self.recorder.options['excludes'] = ['*.out*']
            prob.setup(check=False)
            self.run(prob)

            if not MPI or prob.root.comm.rank == 0:
                expected_params = [
                    ("C1.a", [1.0, 1.0, 1.0]),
                    ("C1.b", [2.0, 2.0, 2.0]),
                ]
                expected_unknowns = [
                    ("C1.c",  np.array([3.0, 3.0, 3.0])),
                    ("C1.d",  np.array([-1.0, -1.0, -1.0])),
                ]
                expected_resids = [
                    ("C1.c",  np.array([0.0, 0.0, 0.0])),
                    ("C1.d",  np.array([0.0, 0.0, 0.0])),
                ]

                expected = (expected_params, expected_unknowns, expected_resids)

                self.assertDatasetEquals(
                    [(['Driver', (1,)], expected)],
                    self.eps
                )

        def test_solver_record(self):
            size = 3

            prob = Problem(Group(), impl=impl)

            G1 = prob.root.add('G1', ParallelGroup())
            G1.add('P1', IndepVarComp('x', np.ones(size, float) * 1.0))
            G1.add('P2', IndepVarComp('x', np.ones(size, float) * 2.0))

            prob.root.add('C1', ABCDArrayComp(size))

            prob.root.connect('G1.P1.x', 'C1.a')
            prob.root.connect('G1.P2.x', 'C1.b')
            prob.root.nl_solver.add_recorder(self.recorder)
            prob.setup(check=False)
            self.run(prob)

            if not MPI or prob.root.comm.rank == 0:

                expected_params = [
                    ("C1.a", [1.0, 1.0, 1.0]),
                    ("C1.b", [2.0, 2.0, 2.0]),
                ]
                expected_unknowns = [
                    ("G1.P1.x", np.array([1.0, 1.0, 1.0])),
                    ("G1.P2.x", np.array([2.0, 2.0, 2.0])),
                    ("C1.c",  np.array([3.0, 3.0, 3.0])),
                    ("C1.d",  np.array([-1.0, -1.0, -1.0])),
                    ("C1.out_string", "_C1"),
                    ("C1.out_list", [1.5]),
                ]
                expected_resids = [
                    ("G1.P1.x", np.array([0.0, 0.0, 0.0])),
                    ("G1.P2.x", np.array([0.0, 0.0, 0.0])),
                    ("C1.c",  np.array([0.0, 0.0, 0.0])),
                    ("C1.d",  np.array([0.0, 0.0, 0.0])),
                    ("C1.out_string", ""),
                    ("C1.out_list", []),
                ]

                expected = (expected_params, expected_unknowns, expected_resids)

                self.assertDatasetEquals(
                    [(['Driver', (1,), "root", (1,)], expected)],
                    self.eps
                )
