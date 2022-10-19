from gurobipy import GRB, LinExpr
from sklearn.utils.validation import check_is_fitted, check_X_y

from odtlearn.flow_opt_ms import FlowOPTMultipleSink
from odtlearn.flow_opt_ss import FlowOPTSingleSink
from odtlearn.utils.callbacks import benders_callback
from odtlearn.utils.validation import (
    check_array,
    check_binary,
    check_columns_match,
    check_ipw,
    check_y,
    check_y_hat,
)


class BendersOPT_IPW(FlowOPTSingleSink):
    def __init__(self, depth=1, time_limit=60, num_threads=None, verbose=False, treatments_filter = None) -> None:
        super().__init__(depth, time_limit, num_threads, verbose, treatments_filter)

        # The cuts we add in the callback function would be treated as lazy constraints
        self._model.params.LazyConstraints = 1
        """
        The following variables are used for the Benders problem to keep track
        of the times we call the callback.

        - counter_integer tracks number of times we call the callback from an
        integer node in the branch-&-bound tree
            - time_integer tracks the associated time spent in the
            callback for these calls
        - counter_general tracks number of times we call the callback from
        a non-integer node in the branch-&-bound tree
            - time_general tracks the associated time spent in the callback for
            these calls

        the ones ending with success are related to success calls.
        By success we mean ending up adding a lazy constraint
        to the model

        """
        self._model._total_callback_time_integer = 0
        self._model._total_callback_time_integer_success = 0

        self._model._total_callback_time_general = 0
        self._model._total_callback_time_general_success = 0

        self._model._callback_counter_integer = 0
        self._model._callback_counter_integer_success = 0

        self._model._callback_counter_general = 0
        self._model._callback_counter_general_success = 0

        # We also pass the following information to the model as we need them in the callback
        self._model._main_grb_obj = self

    def _define_variables(self):
        self._tree_struc_variables()

        # g[i] is the objective value for the sub-problem[i]
        self._g = self._model.addVars(
            self._datapoints, vtype=GRB.CONTINUOUS, ub=1, name="g"
        )

        # we need these in the callback to have access to the value of the decision variables
        self._model._vars_g = self._g
        self._model._vars_b = self._b
        self._model._vars_p = self._p
        self._model._vars_w = self._w

    def _define_constraints(self):
        self._tree_structure_constraints()

    def _define_objective(self):
        # define objective function
        obj = LinExpr(0)
        for i in self._datapoints:
            obj.add(self._g[i] * (self._y[i]) / self._ipw[i])

        self._model.setObjective(obj, GRB.MAXIMIZE)

    def fit(self, X, t, y, ipw):
        """Method to fit the PrescriptiveTree class on the data

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The training input samples.
        t : array-like, shape (n_samples,)
            The treatment values. An array of int.
        y : array-like, shape (n_samples,)
            The observed outcomes upon given treatment t. An array of int.
        ipw : array-like, shape (n_samples,)
            The inverse propensity weight estimates. An array of floats in [0, 1].
        verbose: bool, default=False
            Display Gurobi output.

        Returns
        -------
        self : object
            Returns self.
        """
        # store column information and dtypes if any
        self._extract_metadata(X, y, t)

        # this function returns converted X and t but we retain metadata
        X, t = check_X_y(X, t)

        # need to check that t is discrete, and/or convert -- starts from 0 in accordance with indexing rule
        try:
            t = t.astype(int)
        except TypeError:
            print("The set of treatments must be discrete.")

        assert (
            min(t) == 0 and max(t) == len(set(t)) - 1
        ), "The set of treatments must be discrete starting from {0, 1, ...}"

        # we also need to check on y and ipw/y_hat depending on the method chosen
        y = check_y(X, y)
        self._ipw = check_ipw(X, ipw)

        # Raises ValueError if there is a column that has values other than 0 or 1
        check_binary(X)

        self._create_main_problem()
        self._model.update()
        self._model.optimize(benders_callback)

        self.b_value = self._model.getAttr("X", self._b)
        self.w_value = self._model.getAttr("X", self._w)
        self.p_value = self._model.getAttr("X", self._p)

        # Return the classifier
        return self

    def predict(self, X):
        """Method for making prescriptions using a PrescriptiveTree classifier

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        t : ndarray, shape (n_samples,)
            The prescribed treatments for the input samples.
        """

        # Check if fit had been called
        check_is_fitted(self, ["b_value", "w_value", "p_value"])

        # This will again convert a pandas df to numpy array
        # but we have the column information from when we called fit
        X = check_array(X)

        check_columns_match(self._X_col_labels, X)

        return self._make_prediction(X)


class FlowOPT_IPW(FlowOPTSingleSink):
    """
    An optimal decision tree that prescribes treatments (as opposed to predicting class labels),
    fitted on a binary-valued observational data set.

    Parameters
    ----------
    depth : int
        A parameter specifying the depth of the tree
    time_limit : int
        The given time limit for solving the MIP in seconds
    method : str, default='IPW'
        The method of Prescriptive Trees to run. Choices in ('IPW', 'DM', 'DR), which represents the
        inverse propensity weighting, direct method, and doubly robust methods, respectively
    num_threads: int, default=None
        The number of threads the solver should use

    """

    def __init__(
        self,
        depth=1,
        time_limit=60,
        num_threads=None,
        verbose=False,
    ) -> None:
        super().__init__(
            depth,
            time_limit,
            num_threads,
            verbose,
        )

    def fit(self, X, t, y, ipw):
        """Method to fit the PrescriptiveTree class on the data

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The training input samples.
        t : array-like, shape (n_samples,)
            The treatment values. An array of int.
        y : array-like, shape (n_samples,)
            The observed outcomes upon given treatment t. An array of int.
        ipw : array-like, shape (n_samples,)
            The inverse propensity weight estimates. An array of floats in [0, 1].
        verbose: bool, default=False
            Display Gurobi output.

        Returns
        -------
        self : object
            Returns self.
        """
        # store column information and dtypes if any
        self._extract_metadata(X, y, t)

        # this function returns converted X and t but we retain metadata
        X, t = check_X_y(X, t)

        # need to check that t is discrete, and/or convert -- starts from 0 in accordance with indexing rule
        try:
            t = t.astype(int)
        except TypeError:
            print("The set of treatments must be discrete.")

        assert (
            min(t) == 0 and max(t) == len(set(t)) - 1
        ), "The set of treatments must be discrete starting from {0, 1, ...}"

        # we also need to check on y and ipw/y_hat depending on the method chosen
        y = check_y(X, y)
        self._ipw = check_ipw(X, ipw)

        # Raises ValueError if there is a column that has values other than 0 or 1
        check_binary(X)

        self._create_main_problem()
        self._model.update()
        self._model.optimize()

        self.b_value = self._model.getAttr("X", self._b)
        self.w_value = self._model.getAttr("X", self._w)
        self.p_value = self._model.getAttr("X", self._p)

        # Return the classifier
        return self

    def predict(self, X):
        """Method for making prescriptions using a PrescriptiveTree classifier

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        t : ndarray, shape (n_samples,)
            The prescribed treatments for the input samples.
        """

        # Check if fit had been called
        check_is_fitted(self, ["b_value", "w_value", "p_value"])

        # This will again convert a pandas df to numpy array
        # but we have the column information from when we called fit
        X = check_array(X)

        check_columns_match(self._X_col_labels, X)

        return self._make_prediction(X)


class FlowOPT_DM(FlowOPTMultipleSink):
    def __init__(
        self,
        depth=1,
        time_limit=60,
        num_threads=None,
        verbose=False,
    ) -> None:
        """
        An optimal decision tree that prescribes treatments (as opposed to predicting class labels),
        fitted on a binary-valued observational data set.

        Parameters
        ----------
        depth : int
            A parameter specifying the depth of the tree
        time_limit : int
            The given time limit for solving the MIP in seconds
        num_threads: int, default=None
            The number of threads the solver should use
        verbose: bool, default=False
            Display Gurobi output.

        """
        super().__init__(
            depth,
            time_limit,
            num_threads,
            verbose,
        )

    def _define_objective(self):
        # define objective function
        obj = LinExpr(0)
        for i in self._datapoints:
            for n in self._tree.Nodes + self._tree.Leaves:
                for k in self._treatments:
                    obj.add(
                        self._zeta[i, n, k] * (self._y_hat[i][int(k)])
                    )  # we assume that each column corresponds to an ordered list t, which might be problematic

        self._model.setObjective(obj, GRB.MAXIMIZE)

    def fit(self, X, t, y, y_hat):
        """Method to fit the PrescriptiveTree class on the data

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The training input samples.
        t : array-like, shape (n_samples,)
            The treatment values. An array of int.
        y : array-like, shape (n_samples,)
            The observed outcomes upon given treatment t. An array of int.
        y_hat: array-like, shape (n_samples, n_treatments)
            The counterfactual predictions.


        Returns
        -------
        self : object
            Returns self.
        """
        # store column information and dtypes if any
        self._extract_metadata(X, y, t)

        # this function returns converted X and t but we retain metadata
        X, t = check_X_y(X, t)

        # need to check that t is discrete, and/or convert -- starts from 0 in accordance with indexing rule
        try:
            t = t.astype(int)
        except TypeError:
            print("The set of treatments must be discrete.")

        assert (
            min(t) == 0 and max(t) == len(set(t)) - 1
        ), "The set of treatments must be discrete starting from {0, 1, ...}"

        # we also need to check on y and ipw/y_hat depending on the method chosen
        y = check_y(X, y)
        self._y_hat = check_y_hat(X, self._treatments, y_hat)

        # Raises ValueError if there is a column that has values other than 0 or 1
        check_binary(X)

        self._create_main_problem()
        self._model.update()
        self._model.optimize()

        self.b_value = self._model.getAttr("X", self._b)
        self.w_value = self._model.getAttr("X", self._w)
        self.p_value = self._model.getAttr("X", self._p)

        # Return the classifier
        return self

    def predict(self, X):
        """Classify test points using the StrongTree classifier

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        y : ndarray, shape (n_samples,)
            The label for each sample is the label of the closest sample
            seen during fit.
        """
        # Check is fit had been called
        # for now we are assuming the model has been fit successfully if the fitted values for b, w, and p exist
        check_is_fitted(self, ["b_value", "w_value", "p_value"])

        # This will again convert a pandas df to numpy array
        # but we have the column information from when we called fit
        X = check_array(X)

        check_columns_match(self._X_col_labels, X)

        return self._make_prediction(X)


class FlowOPT_DR(FlowOPTMultipleSink):
    def __init__(self, depth=1, time_limit=60, num_threads=None, verbose=False) -> None:
        """
        An optimal decision tree that prescribes treatments (as opposed to predicting class labels),
        fitted on a binary-valued observational data set.

        Parameters
        ----------
        depth : int
            A parameter specifying the depth of the tree
        time_limit : int
            The given time limit for solving the MIP in seconds
        num_threads: int, default=None
            The number of threads the solver should use
        verbose: bool, default=False
            Display Gurobi output.

        """
        super().__init__(depth, time_limit, num_threads, verbose)

    def fit(self, X, t, y, ipw, y_hat):
        """Method to fit the PrescriptiveTree class on the data

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The training input samples.
        t : array-like, shape (n_samples,)
            The treatment values. An array of int.
        y : array-like, shape (n_samples,)
            The observed outcomes upon given treatment t. An array of int.
        ipw : array-like, shape (n_samples,)
            The inverse propensity weight estimates. An array of floats in [0, 1].
        y_hat: array-like, shape (n_samples, n_treatments)
            The counterfactual predictions.


        Returns
        -------
        self : object
            Returns self.
        """
        # store column information and dtypes if any
        self._extract_metadata(X, y, t)

        # this function returns converted X and t but we retain metadata
        X, t = check_X_y(X, t)

        # need to check that t is discrete, and/or convert -- starts from 0 in accordance with indexing rule
        try:
            t = t.astype(int)
        except TypeError:
            print("The set of treatments must be discrete.")

        assert (
            min(t) == 0 and max(t) == len(set(t)) - 1
        ), "The set of treatments must be discrete starting from {0, 1, ...}"

        # we also need to check on y and ipw/y_hat depending on the method chosen
        y = check_y(X, y)
        self._ipw = check_ipw(X, ipw)
        self._y_hat = check_y_hat(X, self._treatments, y_hat)

        # Raises ValueError if there is a column that has values other than 0 or 1
        check_binary(X)

        self._create_main_problem()
        self._model.update()
        self._model.optimize()

        self.b_value = self._model.getAttr("X", self._b)
        self.w_value = self._model.getAttr("X", self._w)
        self.p_value = self._model.getAttr("X", self._p)

        # Return the classifier
        return self

    def predict(self, X):
        """Classify test points using the StrongTree classifier

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The input samples.

        Returns
        -------
        y : ndarray, shape (n_samples,)
            The label for each sample is the label of the closest sample
            seen during fit.
        """
        # Check is fit had been called
        # for now we are assuming the model has been fit successfully if the fitted values for b, w, and p exist
        check_is_fitted(self, ["b_value", "w_value", "p_value"])

        # This will again convert a pandas df to numpy array
        # but we have the column information from when we called fit
        X = check_array(X)

        check_columns_match(self._X_col_labels, X)

        return self._make_prediction(X)

    def _define_objective(self):
        # define objective function
        obj = LinExpr(0)
        for i in self._datapoints:
            for n in self._tree.Nodes + self._tree.Leaves:
                for k in self._treatments:
                    obj.add(
                        self._zeta[i, n, k] * (self._y_hat[i][int(k)])
                    )  # we assume that each column corresponds to an ordered list t, which might be problematic
                    if self._t[i] == int(k):
                        obj.add(
                            self._zeta[i, n, k]
                            * (self._y[i] - self._y_hat[i][int(k)])
                            / self._ipw[i]
                        )
        self._model.setObjective(obj, GRB.MAXIMIZE)
