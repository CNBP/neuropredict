from __future__ import print_function
import os
import sys
import warnings
import numpy as np
import matplotlib.pyplot as plt
import itertools
from collections import Counter
import random
import pickle
import sklearn
from sklearn.model_selection import cross_val_score
from sklearn.metrics import confusion_matrix
from sklearn.ensemble import RandomForestClassifier

file_name_results = "rhst_results.pkl"

from pyradigm import MLDataset


def eval_optimized_clsfr_on_testset(train_fs, test_fs):
    "Method to optimize the classifier on the training set and return predictions on test set. "

    MAX_DIM_TRAINING = max_dimensionality_to_avoid_curseofdimensionality(train_fs.num_samples)

    NUM_TREES = 50
    MAX_MIN_LEAFSIZE = 20
    SEED_RANDOM = 652

    range_min_leafsize   = range(1, MAX_MIN_LEAFSIZE, 5)
    range_num_predictors = range(1, MAX_DIM_TRAINING, 2)

    # capturing the edge cases
    if len(range_min_leafsize) < 1:
        range_min_leafsize = [ 1 ]
    if len(range_num_predictors) < 1:
        range_num_predictors = [MAX_DIM_TRAINING]

    oob_error_train = np.full([len(range_min_leafsize), len(range_num_predictors)], np.nan)

    train_data_mat, train_labels, _               = train_fs.data_and_labels()
    test_data_mat , test_labels , test_sample_ids = test_fs.data_and_labels()

    for idx_ls, minls in enumerate(range_min_leafsize):
        for idx_np, num_pred in enumerate(range_num_predictors):
            rf = RandomForestClassifier(max_features=num_pred , min_samples_leaf = minls,
                                        n_estimators=NUM_TREES, max_depth=None,
                                        oob_score = True,
                                        random_state=SEED_RANDOM)
            rf.fit(train_data_mat, train_labels)
            oob_error_train[idx_ls, idx_np] = rf.oob_score_

    # identifying the best parameters
    best_idx_ls, best_idx_numpred = np.unravel_index(oob_error_train.argmin(), oob_error_train.shape)
    best_minleafsize    = range_min_leafsize[best_idx_ls]
    best_num_predictors = range_num_predictors[best_idx_numpred]

    # training the RF using the best parameters
    best_rf = RandomForestClassifier( max_features=best_num_predictors, min_samples_leaf=best_minleafsize,
                                      oob_score=True,
                                      n_estimators=NUM_TREES, random_state=SEED_RANDOM)
    best_rf.fit(train_data_mat, train_labels)

    # making predictions on the test set and assessing their performance
    pred_labels = best_rf.predict(test_data_mat)
    feat_importance = best_rf.feature_importances_

    #TODO test if the gathering of prob data is consistent across multiple calls to this method
    #   perhaps by controlling the class order in input
    # The order of the classes corresponds to that in the attribute best_rf.classes_.
    pred_prob = best_rf.predict_proba(test_data_mat)

    conf_mat = confusion_matrix(test_labels, pred_labels)

    misclsfd_samples = test_sample_ids[test_labels != pred_labels]

    return pred_prob, pred_labels,\
           conf_mat, misclsfd_samples, \
           feat_importance, best_minleafsize, best_num_predictors


def display_confusion_matrix(cfmat, class_labels,
                             title='Confusion matrix',
                             display_perc=False,
                             cmap=plt.cm.Blues):
    """
    Display routine for the confusion matrix.
    Entries in confusin matrix can be turned into percentages with `display_perc=True`.
    """

    plt.imshow(cfmat, interpolation='nearest', cmap=cmap)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(class_labels))
    plt.xticks(tick_marks, class_labels, rotation=45)
    plt.yticks(tick_marks, class_labels)

    if display_perc:
        cfmat = cfmat.astype('float') / cfmat.sum(axis=1)[:, np.newaxis]

    # trick from sklearn
    thresh = cfmat.max() / 2.
    for i, j in itertools.product(range(cfmat.shape[0]), range(cfmat.shape[1])):
        plt.text(j, i, cfmat[i, j],
                 horizontalalignment="center",
                 color="white" if cfmat[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('True class')
    plt.xlabel('Predicted class')


def max_dimensionality_to_avoid_curseofdimensionality(num_samples, perc_prob_error_allowed = 0.05):
    """
    Computes the largest dimensionality that can be used to train a predictive model
        avoiding curse of dimensionality for a 5% probability of error.
    Optional argument can specify the amount of error that the user wants to allow (deafult : 5% prob of error ).

    Citation: Michael Fitzpatrick and Milan Sonka, Handbook of Medical Imaging, 2000

    :param num_samples:
    :param perc_prob_error_allowed:
    :return:
    """

    if num_samples < 1/(2*perc_prob_error_allowed):
        max_red_dim = 1
    else:
        max_red_dim = np.floor(num_samples * (2*perc_prob_error_allowed))

    return np.int64(max_red_dim)


def balanced_accuracy(confmat):
    "Computes the balanced accuracy in a given confusion matrix!"
    # IMPLEMENT TODO

    num_classes = confmat.shape[0]
    assert num_classes==confmat.shape[1], "CM is not square!"

    confmat = confmat.astype(np.float64)

    indiv_class_acc = np.full([num_classes,1], np.nan)
    for cc in range(num_classes):
        indiv_class_acc[cc] = confmat[cc,cc] / np.sum(confmat[cc,:])

    bal_acc = np.mean(indiv_class_acc)

    return bal_acc


def save_results(out_dir, var_list_to_save):
    "Serializes the results to disk."

    # LATER choose a more universal serialization method (that could be loaded from a web app)
    try:
        out_results_path = os.path.join(out_dir, file_name_results)
        with open(out_results_path, 'wb') as cfg:
            pickle.dump(var_list_to_save, cfg)
    except:
        raise IOError('Error saving the results to disk!')

    return


def load_results(fpath):
    "Loads the results serialized by RHsT."
    # TODO need to standardize what needs to saved/read back

    try:
        with open(fpath) as rf:
            dataset_paths, train_perc, num_repetitions, num_classes, pred_prob_per_class, pred_labels_per_rep_fs, \
            test_labels_per_rep, best_min_leaf_size, best_num_predictors, feature_importances_rf, misclf_sample_ids, \
            misclf_sample_classes, num_times_misclfd, num_times_tested, confusion_matrix, accuracy_balanced = \
                pickle.load(rf)

        return dataset_paths, train_perc, num_repetitions, num_classes, pred_prob_per_class, pred_labels_per_rep_fs, \
            test_labels_per_rep, best_min_leaf_size, best_num_predictors, feature_importances_rf, misclf_sample_ids, \
            misclf_sample_classes, num_times_misclfd, num_times_tested, confusion_matrix, accuracy_balanced
    except:
        raise IOError("Error reading the results from disk!")

    return


def holdout_evaluation(datasets, train_size_common, total_test_samples):
    "Performs one repetition of the train/test and returns the relevant evaluation metrics."

    num_datasets= len(datasets)
    num_classes = datasets[0].num_classes

    pred_prob_per_class    = np.full([total_test_samples, num_classes], np.nan)
    pred_labels_per_rep_fs = np.full([total_test_samples], np.nan)
    test_labels_per_rep    = np.full([total_test_samples], np.nan)

    best_min_leaf_size  = np.full([num_datasets], np.nan)
    best_num_predictors = np.full([num_datasets], np.nan)

    confusion_matrix  = np.full([num_classes, num_classes, num_datasets], np.nan)
    accuracy_balanced = np.full([num_datasets], np.nan)

    train_set, test_set = datasets[0].train_test_split_ids(count_per_class=train_size_common)

    # evaluating each feature/datasets
    for dd in range(num_datasets):
        print(" feature {:3d}: ".format(dd), end='')

        train_fs = datasets[dd].get_subset(train_set)
        test_fs = datasets[dd].get_subset(test_set)

        pred_prob_per_class[dd, :, :], pred_labels_per_rep_fs[dd, :], \
        confmat, misclsfd_ids_this_run, feature_importances_rf[dd], \
        best_min_leaf_size[dd], best_num_predictors[dd] = \
            eval_optimized_clsfr_on_testset(train_fs, test_fs)

        accuracy_balanced[dd] = balanced_accuracy(confmat)
        confusion_matrix[:, :, dd] = confmat

        print('balanced accuracy: {:.4f}'.format(accuracy_balanced[rep, dd]))

    return pred_prob_per_class, pred_labels_per_rep_fs, \
        confmat, misclsfd_ids_this_run, feature_importances_rf, \
        best_min_leaf_size, best_num_predictors



def run(dataset_path_file, out_results_dir, train_perc = 0.8, num_repetitions = 200):
    """

    :param dataset_path_file: path to file containing list of paths (each containing a valid MLDataset).
    :param out_results_dir: path to save the results to (in various forms)
    :param train_perc: percetange of subjects to train the classifier on. The percentage is applied to the size of
    the smallest class to estimate the numner of subjects from each class to be reserved for training. The smallest
    class is chosen to avoid class-imbalance in the training set. Default: 0.8 (80%).
    :param num_repetitions: number of repetitions of cross-validation estimation. Default: 200.
    :return:
    """

    # load datasets
    # validate each dataset
    # ensure same number of subjects across all datasets
    #        same number of features/subject in each dataset
    #        same class set across all datasets
    # re-map the labels (from 1 to n) to ensure numeric labels do not differ
    # sort them if need be (not needed if MLDatasets)
    # for rep 1 to N, for feat 1 to M,
    #   run train/test/evaluate.
    #   keep tab on misclassifications
    # save results (comprehensive and reloadable manner)

    assert os.path.exists(dataset_path_file), "File containing dataset paths does not exist."
    with open(dataset_path_file, 'r') as dpf:
        dataset_paths = dpf.read().splitlines()

    try:
        out_results_dir = os.path.abspath(out_results_dir)
        if not os.path.exists(out_results_dir):
            os.mkdir(out_results_dir)
    except:
        raise IOError('Error in checking or creating output directiory. Ensure write permissions!')

    num_repetitions = int(num_repetitions)
    assert num_repetitions < np.Inf, "Infinite number of repetitions is not recommened!"
    assert num_repetitions > 1, "More than repetition is necessary!"
    # TODO warning when num_rep are not suficient: need a heuristic to assess it

    # loading datasets
    datasets = list()
    for fp in dataset_paths:
        assert os.path.exists(fp), "Dataset @ {} does not exist.".format(fp)

        try:
            # there is an internal validation of dataset
            ds = MLDataset(fp)
        except:
            print("Dataset @ {} is not a valid MLDataset!".format(fp))
            raise

        # add the valid dataset to list
        datasets.append(ds)

    # ensure same number of subjects across all datasets
    num_datasets = int(len(datasets))
    # looking into the first dataset
    common_ds = datasets[0]
    class_set, label_set, class_sizes = common_ds.summarize_classes()
    num_samples = common_ds.num_samples
    num_classes = len(class_set)

    for idx in range(1, num_datasets):
        this_ds = datasets[idx]
        assert num_samples==this_ds.num_samples, "Number of samples in different datasets differ!"
        assert class_set==set(this_ds.classes.values()), \
            "Classes differ among datasets! \n One dataset: {} \n Another: {}".format(
                class_set, set(this_ds.classes.values()))

    # re-map the labels (from 1 to n) to ensure numeric labels do not differ
    remapped_class_labels = dict()
    for idx, cls in enumerate(class_set):
        remapped_class_labels[cls] = idx

    labels_with_correspondence = dict()
    for subid in common_ds.sample_ids:
        labels_with_correspondence[subid] = remapped_class_labels[common_ds.classes[subid]]

    for idx in range(num_datasets):
        datasets[idx].labels = labels_with_correspondence

    assert (train_perc >= 0.01 and train_perc <= 0.99), \
        "Training percentage {} out of bounds - must be > 0.01 and < 0.99".format(train_perc)

    num_features = np.zeros(num_datasets).astype(np.int64)
    for idx in range(num_datasets):
        num_features[idx] = datasets[idx].num_features

    # determine the common size for training
    print("Different classes in the training set are stratified to match the smallest class!")
    train_size_per_class = np.int64(np.floor(train_perc*class_sizes).astype(np.float64))
    # per-class
    train_size_common = np.int64(np.minimum(min(train_size_per_class), train_size_per_class))
    # single number
    reduced_sizes = np.unique(train_size_common)
    assert len(reduced_sizes)==1, "Error in stratification of training set based on the smallest class!"
    train_size_common = reduced_sizes[0]

    total_test_samples = np.int64(np.sum(class_sizes) - num_classes*train_size_common)

    pred_prob_per_class    = np.full([num_repetitions, num_datasets, total_test_samples, num_classes], np.nan)
    pred_labels_per_rep_fs = np.full([num_repetitions, num_datasets, total_test_samples], np.nan)
    test_labels_per_rep    = np.full([num_repetitions, total_test_samples], np.nan)

    best_min_leaf_size  = np.full([num_repetitions, num_datasets], np.nan)
    best_num_predictors = np.full([num_repetitions, num_datasets], np.nan)

    # initialize misclassification counters
    num_times_tested = list()
    num_times_misclfd= list()
    for dd in range(num_datasets):
        num_times_tested.append(Counter(common_ds.sample_ids))
        num_times_misclfd.append(Counter(common_ds.sample_ids))
        for subid in common_ds.sample_ids:
            num_times_tested[dd][subid] = 0
            num_times_misclfd[dd][subid]= 0

    # num_times_tested  = np.zeros([num_samples, num_datasets])
    # num_times_misclfd = np.zeros([num_samples, num_datasets])

    confusion_matrix  = np.full([num_classes, num_classes, num_repetitions, num_datasets], np.nan)
    accuracy_balanced = np.full([num_repetitions, num_datasets], np.nan)

    feature_importances_rf = [None]*num_datasets
    for idx in range(num_datasets):
        feature_importances_rf[idx] = np.full([num_repetitions,num_features[idx]], np.nan)

    # repeated-hold out CV begins here
    # TODO implement a multi-process version as differnt rep's are embarrasingly parallel
    # use the following one statement processing that can be forked to parallel threads
    # pred_prob_per_class[rep, dd, :, :], pred_labels_per_rep_fs[rep, dd, :], \
    # confmat, misclsfd_ids_this_run, feature_importances_rf[dd][rep, :], \
    # best_min_leaf_size[rep, dd], best_num_predictors[rep, dd] \
    #     = holdout_evaluation(datasets, train_size_common, total_test_samples)

    for rep in range(num_repetitions):
        print(" CV trial {:3d} ".format(rep))

        train_set, test_set = common_ds.train_test_split_ids(count_per_class=train_size_common)
        _ , test_labels_per_rep[rep, :] = test_fs.data_and_labels

        # evaluating each feature/dataset
        # try set test_labels_per_rep outside dd loop as its the same across all dd
        for dd in range(num_datasets):
            print("\t feature {:3d}: ".format(dd), end='')

            train_fs = datasets[dd].get_subset(train_set)
            test_fs  = datasets[dd].get_subset(test_set)

            pred_prob_per_class[rep, dd, :, :], \
                pred_labels_per_rep_fs[rep, dd, :], \
                confmat, misclsfd_ids_this_run, feature_importances_rf[dd][rep,:], \
                best_min_leaf_size[rep, dd], best_num_predictors[rep, dd] = \
                eval_optimized_clsfr_on_testset(train_fs, test_fs)

            accuracy_balanced[rep,dd] = balanced_accuracy(confmat)
            confusion_matrix[:,:,rep,dd] = confmat

            num_times_misclfd[dd].update(misclsfd_ids_this_run)
            num_times_tested[dd].update(test_fs.sample_ids)

            print('balanced accuracy: {:.4f}'.format(accuracy_balanced[rep,dd]))

    # TODO generate visualizations for each feature set as well as a comparative summary!
    # TODO generate a CSV of different metrics for each dataset, as well as a reloadable

    # save results
    var_list_to_save = [dataset_paths, train_perc, num_repetitions, num_classes,
                        pred_prob_per_class, pred_labels_per_rep_fs, test_labels_per_rep,
                        best_min_leaf_size, best_num_predictors, feature_importances_rf,
                        num_times_misclfd, num_times_tested,
                        confusion_matrix, accuracy_balanced ]

    save_results(out_results_dir, var_list_to_save)

    return


if __name__ == '__main__':
    pass