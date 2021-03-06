""" Base class for all systems in OpenMDAO."""

import sys
from fnmatch import fnmatch
from itertools import chain
from six import string_types, iteritems, itervalues, iterkeys

import numpy as np

from openmdao.core.mpi_wrap import MPI
from openmdao.core.options import OptionsDictionary
from collections import OrderedDict
from openmdao.core.vec_wrapper import VecWrapper
from openmdao.core.vec_wrapper import _PlaceholderVecWrapper

class System(object):
    """ Base class for systems in OpenMDAO. When building models, user should
    inherit from `Group` or `Component`"""

    def __init__(self):
        self.name = ''
        self.pathname = ''

        self._subsystems = OrderedDict()
        self._local_subsystems = []

        self._params_dict = OrderedDict()
        self._unknowns_dict = OrderedDict()

        # specify which variables are promoted up to the parent.  Wildcards
        # are allowed.
        self._promotes = ()

        self.comm = None

        # create placeholders for all of the vectors
        self.unknowns = _PlaceholderVecWrapper('unknowns')
        self.resids = _PlaceholderVecWrapper('resids')
        self.params = _PlaceholderVecWrapper('params')
        self.dunknowns = _PlaceholderVecWrapper('dunknowns')
        self.dresids = _PlaceholderVecWrapper('dresids')

        # dicts of vectors used for parallel solution of multiple RHS
        self.dumat = {}
        self.dpmat = {}
        self.drmat = {}

        opt = self.fd_options = OptionsDictionary()
        opt.add_option('force_fd', False,
                       desc="Set to True to finite difference this system.")
        opt.add_option('form', 'forward',
                       values=['forward', 'backward', 'central', 'complex_step'],
                       desc="Finite difference mode. (forward, backward, central) "
                       "You can also set to 'complex_step' to peform the complex "
                       "step method if your components support it.")
        opt.add_option("step_size", 1.0e-6,
                       desc="Default finite difference stepsize")
        opt.add_option("step_type", 'absolute',
                       values=['absolute', 'relative'],
                       desc='Set to absolute, relative')

        self._relevance = None
        self._impl = None

    def __getitem__(self, name):
        """
        Return the variable of the given name from this system.

        Args
        ----
        name : str
            The name of the variable.

        Returns
        -------
        value
            The unflattened value of the given variable.
        """
        msg = "Variable '%s' must be accessed from a containing Group"
        raise RuntimeError(msg % name)

    def _promoted(self, name):
        """Determine if the given variable name is being promoted from this
        `System`.

        Args
        ----
        name : str
            The name of a variable, relative to this `System`.

        Returns
        -------
        bool
            True if the named variable is being promoted from this `System`.

        Raises
        ------
        TypeError
            if the promoted variable specifications are not in a valid format
        """
        if isinstance(self._promotes, string_types):
            raise TypeError("'%s' promotes must be specified as a list, "
                            "tuple or other iterator of strings, but '%s' was specified" %
                            (self.name, self._promotes))

        for prom in self._promotes:
            if fnmatch(name, prom):
                for meta in chain(itervalues(self._params_dict),
                                  itervalues(self._unknowns_dict)):
                    if name == meta.get('promoted_name'):
                        return True

        return False

    def check_setup(self, out_stream=sys.stdout):
        """Write a report to the given stream indicating any potential problems found
        with the current configuration of this ``System``.

        Args
        ----
        out_stream : a file-like object, optional
            Stream where report will be written.
        """
        pass

    def _check_promotes(self):
        """Check that the `System`s promotes are valid. Raise an Exception if there
        are any promotes that do not match at least one variable in the `System`.

        Raises
        ------
        TypeError
            if the promoted variable specifications are not in a valid format

        RuntimeError
            if a promoted variable specification does not match any variables
        """
        if isinstance(self._promotes, string_types):
            raise TypeError("'%s' promotes must be specified as a list, "
                            "tuple or other iterator of strings, but '%s' was specified" %
                            (self.name, self._promotes))

        for prom in self._promotes:
            for name, meta in chain(iteritems(self._params_dict),
                                    iteritems(self._unknowns_dict)):
                if 'promoted_name' in meta:
                    pname = meta['promoted_name']
                else:
                    pname = name
                if fnmatch(pname, prom):
                    break
            else:
                msg = "'%s' promotes '%s' but has no variables matching that specification"
                raise RuntimeError(msg % (self.pathname, prom))

    def subsystems(self, local=False, recurse=False, include_self=False):
        """ Returns an iterator over subsystems.  For `System`, this is an empty list.

        Args
        ----
        local : bool, optional
            If True, only return those `Components` that are local. Default is False.

        recurse : bool, optional
            If True, return all `Components` in the system tree, subject to
            the value of the local arg. Default is False.

        typ : type, optional
            If a class is specified here, only those subsystems that are instances
            of that type will be returned.  Default type is `System`.

        include_self : bool, optional
            If True, yield self before iterating over subsystems, assuming type
            of self is appropriate. Default is False.

        Returns
        -------
        iterator
            Iterator over subsystems.
        """
        if include_self:
            yield self

    def _setup_paths(self, parent_path):
        """Set the absolute pathname of each `System` in the tree.

        Parameter
        ---------
        parent_path : str
            The pathname of the parent `System`, which is to be prepended to the
            name of this child `System`.
        """
        self._fd_params = None

        if parent_path:
            self.pathname = '.'.join((parent_path, self.name))
        else:
            self.pathname = self.name

    def solve_linear(self, dumat, drmat, vois, mode=None):
        """
        Single linear solution applied to whatever input is sitting in
        the rhs vector.

        Args
        ----
        dumat : dict of `VecWrappers`
            In forward mode, each `VecWrapper` contains the incoming vector
            for the states. There is one vector per quantity of interest for
            this problem. In reverse mode, it contains the outgoing vector for
            the states. (du)

        drmat : `dict of VecWrappers`
            `VecWrapper` containing either the outgoing result in forward mode
            or the incoming vector in reverse mode. There is one vector per
            quantity of interest for this problem. (dr)

        vois : list of strings
            List of all quantities of interest to key into the mats.

        mode : string
            Derivative mode, can be 'fwd' or 'rev', but generally should be
            called without mode so that the user can set the mode in this
            system's ln_solver.options.
        """
        pass

    def is_active(self):
        """
        Returns
        -------
        bool
            If running under MPI, returns True if this `System` has a valid
            communicator. Always returns True if not running under MPI.
        """
        return MPI is None or not (self.comm is None or
                                   self.comm == MPI.COMM_NULL)

    def get_req_procs(self):
        """
        Returns
        -------
        tuple
            A tuple of the form (min_procs, max_procs), indicating the min and max
            processors usable by this `System`.
        """
        return (1, 1)

    def _setup_communicators(self, comm):
        """
        Assign communicator to this `System` and all of its subsystems.

        Args
        ----
        comm : an MPI communicator (real or fake)
            The communicator being offered by the parent system.
        """
        minp, maxp = self.get_req_procs()
        if MPI and comm is not None and comm != MPI.COMM_NULL and comm.size < minp: # pragma: no cover
            raise RuntimeError("%s needs %d MPI processes, but was given only %d." %
                              (self.pathname, minp, comm.size))

        self.comm = comm

    def _set_vars_as_remote(self):
        """
        Set 'remote' attribute in metadata of all variables for this subsystem.
        """
        for meta in itervalues(self._params_dict):
            meta['remote'] = True

        for meta in itervalues(self._unknowns_dict):
            meta['remote'] = True

    def fd_jacobian(self, params, unknowns, resids, total_derivs=False,
                    fd_params=None, fd_unknowns=None, desvar_indices=None):
        """Finite difference across all unknowns in this system w.r.t. all
        incoming params.

        Args
        ----
        params : `VecWrapper`
            `VecWrapper` containing parameters. (p)

        unknowns : `VecWrapper`
            `VecWrapper` containing outputs and states. (u)

        resids : `VecWrapper`
            `VecWrapper` containing residuals. (r)

        total_derivs : bool, optional
            Set to true to calculate total derivatives. Otherwise, partial
            derivatives are returned.

        fd_params : list of strings, optional
            List of parameter name strings with respect to which derivatives
            are desired. This is used by problem to limit the derivatives that
            are taken.

        fd_unknowns : list of strings, optional
            List of output or state name strings for derivatives to be
            calculated. This is used by problem to limit the derivatives that
            are taken.

        desvar_incides: dict of list of integers, optional
            This is a dict that contains the index values for each param that
            was declared, so that we only finite difference those
            indices.

        Returns
        -------
        dict
            Dictionary whose keys are tuples of the form ('unknown', 'param')
            and whose values are ndarrays containing the derivative for that
            tuple pair.
        """

        # Params and Unknowns that we provide at this level.
        if fd_params is None:
            fd_params = self._get_fd_params()
        if fd_unknowns is None:
            fd_unknowns = self._get_fd_unknowns()

        # Use settings in the system dict unless variables override.
        step_size = self.fd_options.get('step_size', 1.0e-6)
        form = self.fd_options.get('form', 'forward')
        step_type = self.fd_options.get('step_type', 'relative')

        jac = {}
        cache2 = None

        # Prepare for calculating partial derivatives or total derivatives
        if total_derivs is False:
            run_model = self.apply_nonlinear
            resultvec = resids
            states = self.states
        else:
            run_model = self.solve_nonlinear
            resultvec = unknowns
            states = []

        cache1 = resultvec.vec.copy()

        gather_jac = False

        # Compute gradient for this param or state.
        for p_name in chain(fd_params, states):

            # If our input is connected to a IndepVarComp, then we need to twiddle
            # the unknowns vector instead of the params vector.
            param_src = self.connections.get(p_name)
            if param_src is not None:

                # Have to convert to promoted name to key into unknowns
                if param_src not in self.unknowns:
                    param_src = self.unknowns.get_promoted_varname(param_src)

                target_input = unknowns.flat[param_src]

            else:
                # Cases where the IndepVarComp is somewhere above us.
                if p_name in states:
                    inputs = unknowns
                else:
                    inputs = params

                target_input = inputs.flat[p_name]

            mydict = {}
            if p_name in self._to_abs_pnames:
                for val in itervalues(self._params_dict):
                    if val['promoted_name'] == p_name:
                        mydict = val
                        break

            # Local settings for this var trump all
            fdstep = mydict.get('step_size', step_size)
            fdtype = mydict.get('step_type', step_type)
            fdform = mydict.get('form', form)

            # Size our Inputs
            if desvar_indices is not None and param_src in desvar_indices:
                idxes = desvar_indices[param_src]
                p_size = len(idxes)
            else:
                p_size = np.size(target_input)
                idxes = range(p_size)

            # Size our Outputs
            for u_name in fd_unknowns:
                u_size = np.size(unknowns[u_name])
                jac[u_name, p_name] = np.zeros((u_size, p_size))

            # if a given param isn't present in this process, we need
            # to still run the model once for each entry in that param
            # in order to stay in sync with the other processes.
            if p_size == 0:
                gather_jac = True
                for i in range(self._params_dict[p_name]['size']):
                    run_model(params, unknowns, resids)

            # Finite Difference each index in array
            for j, idx in enumerate(idxes):

                # Relative or Absolute step size
                if fdtype == 'relative':
                    step = target_input[idx] * fdstep
                    if step < fdstep:
                        step = fdstep
                else:
                    step = fdstep

                if fdform == 'forward':

                    target_input[idx] += step

                    run_model(params, unknowns, resids)

                    target_input[idx] -= step

                    # delta resid is delta unknown
                    resultvec.vec[:] -= cache1
                    resultvec.vec[:] *= (1.0/step)

                elif fdform == 'backward':

                    target_input[idx] -= step

                    run_model(params, unknowns, resids)

                    target_input[idx] += step

                    # delta resid is delta unknown
                    resultvec.vec[:] -= cache1
                    resultvec.vec[:] *= (-1.0/step)

                elif fdform == 'central':

                    target_input[idx] += step

                    run_model(params, unknowns, resids)
                    cache2 = resultvec.vec.copy()

                    target_input[idx] -= step
                    resultvec.vec[:] = cache1

                    target_input[idx] -= step

                    run_model(params, unknowns, resids)

                    # central difference formula
                    resultvec.vec[:] -= cache2
                    resultvec.vec[:] *= (-0.5/step)

                    target_input[idx] += step

                for u_name in fd_unknowns:
                    jac[u_name, p_name][:, j] = resultvec.flat[u_name]

                # Restore old residual
                resultvec.vec[:] = cache1

        if MPI and gather_jac: # pragma: no cover
            jac = self.get_combined_jac(jac)

        return jac

    def _apply_linear_jac(self, params, unknowns, dparams, dunknowns, dresids, mode):
        """ See apply_linear. This method allows the framework to override
        any derivative specification in any `Component` or `Group` to perform
        finite difference."""

        if not self._jacobian_cache:
            msg = ("No derivatives defined for Component '{name}'")
            msg = msg.format(name=self.name)
            raise ValueError(msg)

        isvw = isinstance(dresids, VecWrapper)
        fwd = mode == 'fwd'
        try:
            states = self.states
        except AttributeError:  # handle component unit test where setup has not been performed
            # TODO: should we force all component unit tests to use a Problem test harness?
            states = set([p for u,p in iterkeys(self._jacobian_cache)
                             if p not in dparams])

        for (unknown, param), J in iteritems(self._jacobian_cache):
            if param in states:
                arg_vec = dunknowns
            else:
                arg_vec = dparams

            # Vectors are flipped during adjoint

            try:
                if isvw:
                    if fwd:
                        vec = dresids._flat(unknown)
                        vec += J.dot(arg_vec._flat(param))
                    else:
                        shape = arg_vec._vardict[param]['shape']
                        arg_vec[param] += J.T.dot(dresids._flat(unknown)).reshape(shape)
                else: # plain dicts were passed in for unit testing...
                    if fwd:
                        vec = dresids[unknown]
                        vec += J.dot(arg_vec[param].flat).reshape(vec.shape)
                    else:
                        shape = arg_vec[param].shape
                        arg_vec[param] += J.T.dot(dresids[unknown].flat).reshape(shape)
            except KeyError:
                continue # either didn't find param in dparams/dunknowns or
                         # didn't find unknown in dresids

    def _create_views(self, top_unknowns, parent, my_params,
                      var_of_interest=None):
        """
        A manager of the data transfer of a possibly distributed collection of
        variables.  The variables are based on views into an existing
        `VecWrapper`.

        Args
        ----
        top_unknowns : `VecWrapper`
            The `Problem` level unknowns `VecWrapper`.

        parent : `System`
            The `System` which provides the `VecWrapper` on which to create views.

        my_params : list
            List of pathnames for parameters that this `Group` is
            responsible for propagating.

        relevance : `Relevance`
            Object containing relevance info for each variable of interest.

        var_of_interest : str
            The name of a variable of interest.

        """

        comm = self.comm
        params_dict = self._params_dict
        voi = var_of_interest
        relevance = self._relevance

        # map promoted name in parent to corresponding promoted name in this view
        umap = self._relname_map

        if voi is None:
            self.unknowns = parent.unknowns.get_view(self.pathname, comm, umap)
            self.states = set((n for n,m in iteritems(self.unknowns) if m.get('state')))
            self.resids = parent.resids.get_view(self.pathname, comm, umap)
            self.params = parent._impl.create_tgt_vecwrapper(self.pathname, comm)
            self.params.setup(parent.params, params_dict, top_unknowns,
                              my_params, self.connections, relevance=relevance,
                              store_byobjs=True)

        self.dumat[voi] = parent.dumat[voi].get_view(self.pathname, comm, umap)
        self.drmat[voi] = parent.drmat[voi].get_view(self.pathname, comm, umap)
        self.dpmat[voi] = parent._impl.create_tgt_vecwrapper(self.pathname, comm)

        self.dpmat[voi].setup(parent.dpmat[voi], params_dict, top_unknowns,
                              my_params, self.connections,
                              relevance=relevance, var_of_interest=voi)

    def _setup_gs_outputs(self, vois):
        self.gs_outputs = { 'fwd': {}, 'rev': {}}
        dumat = self.dumat
        gso = self.gs_outputs['fwd']
        for sub in self._local_subsystems:
            gso[sub.name] = outs = {}
            for voi in vois:
                outs[voi] = set([x for x in dumat[voi] if
                                           sub.dumat and x not in sub.dumat[voi]])
        gso = self.gs_outputs['rev']
        for sub in reversed(self._local_subsystems):
            gso[sub.name] = outs = {}
            for voi in vois:
                outs[voi] = set([x for x in dumat[voi] if
                                           not sub.dumat or
                                           (sub.dumat and x not in sub.dumat[voi])])

    def get_combined_jac(self, J):
        """
        Take a J dict that's distributed, i.e., has different values across
        different MPI processes, and return a dict that contains all of the
        values from all of the processes. If values are duplicated, use the
        value from the lowest rank process. Note that J has a nested dict
        structure.

        Args
        ----
        J : `dict`
            Local Jacobian

        Returns
        -------
        `dict`
            Local gathered Jacobian
        """

        if not self.is_active():
            return J

        comm = self.comm
        iproc = comm.rank
        nproc = comm.size

        need_tups = []
        has_tups = []

        # Gather a list of local tuples for J.
        for (output, param), value in iteritems(J):
            if value.size == 0:
                need_tups.append((output, param))
            else:
                has_tups.append((output, param))

        dist_need_tups = comm.allgather(need_tups)

        needed_set = set()
        for need_tups in dist_need_tups:
            needed_set.update(need_tups)

        if not needed_set:
            return J  # nobody needs any J entries

        dist_has_tups = comm.allgather(has_tups)

        found = set()
        owned_vals = []
        for rank, tups in enumerate(dist_has_tups):
            for tup in tups:
                if tup in needed_set and not tup in found:
                    found.add(tup)
                    if rank == iproc:
                        owned_vals.append((tup, J[tup]))

        dist_vals = comm.allgather(owned_vals)

        for rank, vals in enumerate(dist_vals):
            if rank != iproc:
                for (output, param), value in vals:
                    J[output, param] = value

        return J

    def _get_var_pathname(self, name):
        if self.pathname:
            return '.'.join((self.pathname, name))
        return name

    def generate_docstring(self):
        """
        Generates a numpy-style docstring for a user-created System class.

        Returns
        -------
        docstring : str
                string that contains a basic numpy docstring.

        """
        #start the docstring off
        docstring = '    \"\"\"\n'

        if self._params_dict or self._unknowns_dict:
            docstring += '\n    Params\n    ----------\n'

        if self._params_dict:
            for key, value in self._params_dict.items():
                #docstring += type(value).__name__
                docstring += "    " + key + ": param ({"
                #get the values out in order
                dictItemCount = len(value)
                dictPosition = 1
                for k in sorted(value):
                    docstring +=  "'" +k+ "'" + ": " + str(value[k])
                    #don't want a trailing comma
                    if (dictPosition != dictItemCount):
                        docstring += ", "
                    dictPosition += 1
                docstring += "})\n"

        if self._unknowns_dict:
            for key, value in self._unknowns_dict.items():
                docstring += "    " + key + " : unknown ({"
                dictItemCount = len(value)
                dictPosition = 1
                for k in sorted(value):
                    docstring += "'" +k+ "'" + ": " + str(value[k])
                    if (dictPosition != dictItemCount):
                        docstring += ", "
                    dictPosition += 1
                docstring += "})\n"

        #Put options into docstring
        from openmdao.core.options import OptionsDictionary
        firstTime = 1
        #for py3.4, items from vars must come out in same order.
        v = OrderedDict(sorted(vars(self).items()))
        for key, value in v.items():
            if type(value)==OptionsDictionary:
                if firstTime:  #start of Options docstring
                    docstring += '\n    Options\n    -------\n'
                    firstTime = 0
                for (name, val) in sorted(value.items()):
                    docstring += "    " + key + "['"
                    docstring += name + "']"
                    docstring += " :  " + type(val).__name__
                    docstring += "("
                    if type(val).__name__ == 'str': docstring += "'"
                    docstring += str(val)
                    if type(val).__name__ == 'str': docstring += "'"
                    docstring += ")\n"

                    desc = value._options[name]['desc']
                    if(desc):
                        docstring += "        " + desc + "\n"

        #finish up docstring
        docstring += '\n    \"\"\"\n'
        return docstring

def _iter_J_nested(J):
    for output, subdict in iteritems(J):
        for param, value in iteritems(subdict):
            yield (output, param), value
