import numpy as np
from hmmlearn import hmm, _utils
from sklearn.utils import check_array, check_random_state
from hmmlearn.base import _log
from scipy.stats import multinomial
from tqdm.auto import tqdm


class SentenceMultinomialHMM2(hmm.MultinomialHMM):
    def _check_and_set_multinomial_n_features_n_trials(self, X):
        """
        Check if ``X`` is a sample from a multinomial distribution, i.e. an
        array of non-negative integers, summing up to n_trials.
        """
        n_samples, n_features = X.shape
        self.n_features = n_features

        if not np.issubdtype(X.dtype, np.integer) or X.min() < 0:
            raise ValueError("Symbol counts should be nonnegative integers")

    def _compute_log_likelihood(self, X):
        """X is modified from the original. Now is a tuple containing (X, self.n_trials).
        Allows for a variable number of trials per multinomial.
        """
        logprobs = []
        n_trials = self.n_trials
        if n_trials is None:
            n_trials = X.sum(axis=1)

        for component in range(self.n_components):
            score = multinomial.logpmf(
                X, n=n_trials, p=self.emissionprob_[component, :])
            logprobs.append(score)
        return np.vstack(logprobs).T


class SentenceMultinomialHMM(hmm.MultinomialHMM):
    def _check_and_set_multinomial_n_features_n_trials(self, X):
        """
        Check if ``X`` is a sample from a multinomial distribution, i.e. an
        array of non-negative integers, summing up to n_trials.
        """
        n_samples, n_features = X.shape
        self.n_features = n_features

        if not np.issubdtype(X.dtype, np.integer) or X.min() < 0:
            raise ValueError("Symbol counts should be nonnegative integers")

        sample_n_trials = X.sum(axis=1)
        if self.n_trials is None:
            self.n_trials = sample_n_trials

        if not (X.sum(axis=1) == self.n_trials).all():
            raise ValueError("Total count for each sample should add up to "
                             "the number of trials")

    def _compute_log_likelihood(self, X_chunk):
        """X is modified from the original. Now is a tuple containing (X, self.n_trials).
        Allows for a variable number of trials per multinomial.
        """
        X, n_trials = X_chunk
        logprobs = []
        for component in range(self.n_components):
            score = multinomial.logpmf(
                X, n=n_trials, p=self.emissionprob_[component, :])
            logprobs.append(score)
        return np.vstack(logprobs).T

    def fit(self, X, lengths=None):
        """
        Estimate model parameters.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Feature matrix of individual samples.
        lengths : array-like of integers, shape (n_sequences, )
            Lengths of the individual sequences in ``X``. The sum of
            these should be ``n_samples``.

        Returns
        -------
        self : object
            Returns self.
        """
        X = check_array(X)
        self._init(X)
        self._check()

        self.monitor_._reset()
        impl = {
            "scaling": self._fit_scaling,
            "log": self._fit_log,
        }[self.implementation]

        for iter in tqdm(range(self.n_iter)):
            stats = self._initialize_sufficient_statistics()
            curr_log_prob = 0
            if isinstance(self.n_trials, int):
                components = zip(_utils.split_X_lengths(X, lengths), [self.n_trials] * len(lengths))
            else:
                components = zip(_utils.split_X_lengths(X, lengths), _utils.split_X_lengths(self.n_trials, lengths))

            for sub_X, sub_n in tqdm(components, total=len(lengths)):
                lattice, log_prob, posteriors, fwdlattice, bwdlattice = \
                        impl((sub_X, sub_n))

                self._accumulate_sufficient_statistics(
                    stats, sub_X, lattice, posteriors, fwdlattice,
                    bwdlattice
                )
                curr_log_prob += log_prob

            self._do_mstep(stats)

            self.monitor_.report(curr_log_prob)
            if self.monitor_.converged:
                break

        if (self.transmat_.sum(axis=1) == 0).any():
            _log.warning("Some rows of transmat_ have zero sum because no "
                         "transition from the state was ever observed.")

        return self



def sentence2counts(sentence):
    ans = []
    for word, idx in vocab2id.items():
        count = sentence.count(word)
        ans.append(count)
    return ans


# For this example, we will model the stages of a conversation,
# where each sentence is "generated" with an underlying topic, "cat" or "dog"
states = ["cat", "dog"]
id2topic = dict(zip(range(len(states)), states))
# we are more likely to talk about cats first
start_probs = np.array([0.6, 0.4])

# For each topic, the probability of saying certain words can be modeled by
# a distribution over vocabulary associated with the categories

vocabulary = ["tail", "fetch", "mouse", "food"]
# if the topic is "cat", we are more likely to talk about "mouse"
# if the topic is "dog", we are more likely to talk about "fetch"
emission_probs = np.array([[0.25, 0.1, 0.4, 0.25],
                           [0.2, 0.5, 0.1, 0.2]])

# Also assume it's more likely to stay in a state than transition to the other
trans_mat = np.array([[0.8, 0.2], [0.2, 0.8]])

# Pretend that every sentence we speak only has a total of 5 words,
# i.e. we independently utter a word from the vocabulary 5 times per sentence
# we observe the following bag of words (BoW) for 8 sentences:
observations = [
    ["tail", "mouse", "mouse", "food", "mouse"],
    ["food", "mouse", "mouse", "food", "mouse"],
    ["tail", "mouse", "mouse", "tail", "mouse"],
    ["food", "mouse", "food", "food", "tail"],
    ["tail", "fetch", "mouse", "food", "tail"],
    ["tail", "fetch", "fetch", "food", "fetch"],
    ["fetch", "fetch", "fetch", "food", "tail"],
    ["food", "mouse", "food", "food", "tail"],
    ["tail", "mouse", "mouse", "tail", "mouse"],
    ["fetch", "fetch", "fetch", "fetch", "fetch", "fetch"]
]

# Convert "sentences" to numbers:
vocab2id = dict(zip(vocabulary, range(len(vocabulary))))
X = []
for sentence in observations:
    row = sentence2counts(sentence)
    X.append(row)

data = np.array(X, dtype=int)

# pretend this is repeated, so we have more data to learn from:
lengths = [len(X)]*5
sequences = np.tile(data, (5,1))


# Set up model:
model = SentenceMultinomialHMM2(
    n_components=len(states),
    # n_trials=sequences.sum(axis=1),
    n_iter=50,
    init_params='ste'
)

model.fit(sequences, lengths)