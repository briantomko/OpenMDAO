""" Testing group-level finite difference. """

import unittest

import numpy as np
from six import PY3

from openmdao.core import Group, Problem
from openmdao.core.checks import ConnectError
from openmdao.components import IndepVarComp, ExecComp

from openmdao.test.simple_comps import SimpleComp, SimpleArrayComp
from openmdao.test.util import assert_rel_error

if PY3:
    def py3fix(s):
        return s.replace('<type', '<class')
else:
    def py3fix(s):
        return s


class TestIndices(unittest.TestCase):

    def test_indices(self):
        size = 10

        root = Group()

        root.add('P1', IndepVarComp('x', np.zeros(size)))
        root.add('C1', ExecComp('y = x * 2.', y=np.zeros(size//2), x=np.zeros(size//2)))
        root.add('C2', ExecComp('y = x * 3.', y=np.zeros(size//2), x=np.zeros(size//2)))

        root.connect('P1.x', "C1.x", src_indices=list(range(size//2)))
        root.connect('P1.x', "C2.x", src_indices=list(range(size//2, size)))

        prob = Problem(root)
        prob.setup(check=False)

        root.P1.unknowns['x'][0:size//2] += 1.0
        root.P1.unknowns['x'][size//2:size] -= 1.0

        prob.run()

        assert_rel_error(self, root.C1.params['x'], np.ones(size//2), 0.0001)
        assert_rel_error(self, root.C2.params['x'], -np.ones(size//2), 0.0001)

    def test_array_to_scalar(self):
        root = Group()

        root.add('P1', IndepVarComp('x', np.array([2., 3.])))
        root.add('C1', SimpleComp())
        root.add('C2', ExecComp('y = x * 3.', y=0., x=0.))

        root.connect('P1.x', 'C1.x', src_indices=[0,])
        root.connect('P1.x', 'C2.x', src_indices=[1,])

        prob = Problem(root)
        prob.setup(check=False)
        prob.run()

        self.assertAlmostEqual(root.C1.params['x'], 2.)
        self.assertAlmostEqual(root.C2.params['x'], 3.)

    def test_subarray_to_promoted_var(self):
        root = Group()

        P = root.add('P', IndepVarComp('x', np.array([1., 2., 3., 4., 5.])))
        G = root.add('G', Group())
        C = root.add('C', SimpleComp())

        A  = G.add('A', SimpleArrayComp())
        G2 = G.add('G2', Group())

        A2 = G2.add('A2', SimpleArrayComp())

        root.connect('P.x', 'G.A.x', src_indices=[0,1])
        root.connect('P.x', 'C.x', src_indices=[2,])
        root.connect('P.x', 'G.G2.A2.x', src_indices=[3, 4])

        prob = Problem(root)
        prob.setup(check=False)
        prob.run()

        assert_rel_error(self, root.G.A.params['x'], np.array([1., 2.]), 0.0001)
        self.assertAlmostEqual(root.C.params['x'], 3.)
        assert_rel_error(self, root.G.G2.A2.params['x'], np.array([4., 5.]), 0.0001)

        # now try the same thing with promoted var
        root = Group()

        P = root.add('P', IndepVarComp('x', np.array([1., 2., 3., 4., 5.])))
        G = root.add('G', Group())
        C = root.add('C', SimpleComp())

        A  = G.add('A', SimpleArrayComp(), promotes=['x', 'y'])
        G2 = G.add('G2', Group())

        A2 = G2.add('A2', SimpleArrayComp(), promotes=['x', 'y'])

        root.connect('P.x', 'G.x', src_indices=[0,1])
        root.connect('P.x', 'C.x', src_indices=[2,])
        root.connect('P.x', 'G.G2.x', src_indices=[3, 4])

        prob = Problem(root)
        prob.setup(check=False)
        prob.run()

        assert_rel_error(self, root.G.A.params['x'], np.array([1., 2.]), 0.0001)
        self.assertAlmostEqual(root.C.params['x'], 3.)
        assert_rel_error(self, root.G.G2.A2.params['x'], np.array([4., 5.]), 0.0001)

    def test_indices_connect_error(self):
        root = Group()

        P = root.add('P', IndepVarComp('x', np.array([1., 2., 3., 4., 5.])))
        G = root.add('G', Group())
        C = root.add('C', SimpleComp())

        A  = G.add('A', SimpleArrayComp())

        root.connect('P.x', 'G.A.x', src_indices=[0])
        root.connect('P.x', 'C.x', src_indices=[2,])

        expected_error_message = py3fix("Size 1 of the indexed sub-part of "
                                        "source 'P.x' must match the size "
                                        "'2' of the target 'G.A.x'")
        prob = Problem(root)
        with self.assertRaises(ConnectError) as cm:
            prob.setup(check=False)

        self.assertEqual(str(cm.exception), expected_error_message)

        # now try the same thing with promoted var
        root = Group()

        P = root.add('P', IndepVarComp('x', np.array([1., 2., 3., 4., 5.])))
        G = root.add('G', Group())
        C = root.add('C', SimpleComp())

        A  = G.add('A', SimpleArrayComp(), promotes=['x', 'y'])

        root.connect('P.x', 'G.x', src_indices=[0,1,2])
        root.connect('P.x', 'C.x', src_indices=[2,])

        expected_error_message = py3fix("Size 3 of the indexed sub-part of "
                                        "source 'P.x' must match the size "
                                        "'2' of the target 'G.x'")
        prob = Problem(root)
        with self.assertRaises(ConnectError) as cm:
            prob.setup(check=False)

        self.assertEqual(str(cm.exception), expected_error_message)


if __name__ == "__main__":
    unittest.main()
