#/usr/bin/python

import sys
import os
import nibabel
import sklearn
import argparse
import warnings
import pickle
from time import localtime, strftime

from freesurfer import *
from pyradigm import MLDataset
import rhst
import visualize

import config_neuropredict as cfg

def make_time_stamp():
    "Returns a timestamp string."

    # just by the hour
    return strftime('%Y%m%d-T%H', localtime())

def not_unspecified( var ):
    """ Checks for null values of a give variable! """

    return var not in [ 'None', None, '' ]


def parse_args():
    """Parser/validator for the cmd line args."""

    parser = argparse.ArgumentParser(prog="neuropredict")

    parser.add_argument("-m", "--metadatafile", action="store", dest="metadatafile",
                        default=None, required=True,
                        help="Abs path to file containing metadata for subjects to be included for analysis. At the "
                             "minimum, each subject should have an id per row followed by the class it belongs to. "
                             "E.g. \n"
                             "sub001,control\n"
                             "sub002,control\n"
                             "sub003,disease\n"
                             "sub004,disease\n")

    parser.add_argument("-o", "--outdir", action="store", dest="outdir",
                        required=True,
                        help="Output folder to store features and results.")

    parser.add_argument("-f", "--fsdir", action="store", dest="fsdir",
                        default=None,
                        help="Absolute path to SUBJECTS_DIR containing the finished runs of Freesurfer parcellation"
                             " (each subject named after its ID in the metadata file)")

    parser.add_argument("-u", "--userdir", action="store", dest="userdir",
                        nargs = '+', # to allow for multiple features
                        default=None,
                        help="List of absolute paths to an user's own features."
                             "Each folder contains a separate folder for each subject "
                             "  (named after its ID in the metadata file) "
                             "containing a file called features.txt with one number per line.\n"
                             "All the subjects (in a given folder) must have the number of features (#lines in file). "
                             "Different folders can have different number of features for each subject."
                             "\n Names of each folder is used to annotate the results in visualizations. "
                             "Hence name them uniquely and meaningfully, keeping in mind these figures will be included in your papers.")

    parser.add_argument("-p", "--positiveclass", action="store", dest="positiveclass",
                        default=None,
                        help="Name of the positive class (Alzheimers, MCI or Parkinsons etc) "
                             "to be used in calculation of area under the ROC curve. "
                             "Default: class appearning second in order specified in metadata file.")

    parser.add_argument("-t", "--trainperc", action="store", dest="train_perc",
                        default=0.5,
                        help="Percentage of the smallest class to be reserved for training. "
                             "Must be in the interval [0.01 0.99]."
                             "If sample size is sufficiently big, we recommend 0.5."
                             "If sample size is small, or class imbalance is high, choose 0.8.")

    parser.add_argument("-n", "--numrep", action="store", dest="num_rep_cv",
                        default=200,
                        help="Number of repetitions of the repeated-holdout cross-validation. "
                             "The larger the number, the better the estimates will be.")

    parser.add_argument("-a", "--atlas", action="store", dest="atlasid",
                        default="fsaverage",
                        help="Name of the atlas to use for visualization."
                             "\nDefault: fsaverage, if available.")

    if len(sys.argv) < 2:
        print('Too few arguments!')
        parser.print_help()
        parser.exit(1)

    # parsing
    try:
        options = parser.parse_args()
    except:
        parser.exit(1)

    # noinspection PyUnboundLocalVariable
    metadatafile = os.path.abspath(options.metadatafile)
    assert os.path.exists(metadatafile), "Given metadata file doesn't exist."

    atleast_one_feature_specified = False
    if not_unspecified(options.fsdir):
        fsdir = os.path.abspath(options.fsdir)
        assert os.path.exists(fsdir), "Given Freesurfer directory doesn't exist."
        atleast_one_feature_specified = True
    else:
        fsdir = None

    if not_unspecified(options.userdir):
        userdir = map(os.path.abspath, options.userdir)
        for udir in userdir:
            assert os.path.exists(udir), "One of the user directories for features doesn't exist:" \
                                         "\n {}".format(udir)
        atleast_one_feature_specified = True
    else:
        userdir = None

    if not atleast_one_feature_specified:
        raise ValueError('Atleast a Freesurfer directory or one user-defined directory must be specified.')

    outdir = os.path.abspath(options.outdir)
    if not os.path.exists(outdir):
        try:
            os.mkdir(outdir)
        except:
            raise

    train_perc = np.float32(options.train_perc)
    assert (train_perc >= 0.01 and train_perc <= 0.99), \
        "Training percentage {} out of bounds - must be > 0.01 and < 0.99".format(train_perc)

    num_rep_cv = np.int64(options.num_rep_cv)
    assert num_rep_cv >= 10, \
        "Atleast 10 repitions of CV is recommened.".format(train_perc)

    return metadatafile, outdir, userdir, fsdir, \
           train_perc, num_rep_cv, options.positiveclass


def get_metadata(path):
    """
    Populates the dataset dictionary with subject ids and classes

    Currently supports the following per line: subjectid,class
    Future plans to include demographics data: subjectid,class,age,sex,education

    """

    sample_ids = list()
    classes = dict()
    with open(path) as mf:
        for line in mf:
            if not line.startswith('#'):
                parts = line.strip().split(',')
                sid = parts[0]
                sample_ids.append(sid)
                classes[sid] = parts[1]

    return sample_ids, classes


def userdefinedget(featdir, subjid):
    """
    Method to read in features for a given subject from a user-defined feature folder. This featdir must contain a
    separate folder for each subject with a file called features.txt with one number per line.
    
    Parameters
    ----------
    featdir : str
        Path to in the input directory
    subjid : str
        Subject id (name of the subfolder in the featdir identifying the subject)

    Returns
    -------
    data : ndarray 
        vector of features for the given subject
    feat_names : list of str
        names of each feature
        Currently None.
    """

    feat_names = None

    featfile = os.path.join(featdir, subjid, 'features.txt')
    data = np.genfromtxt(featfile)

    return data, feat_names


def getfeatures(subjects, classes, featdir, outdir, outname, getmethod = None):
    """Populates the pyradigm data structure with features from a given method.

    getmethod: takes in a path and returns a vectorized feature set (e.g. set of subcortical volumes),
        with an optional array of names for each feature.
    classes: dict of class labels keyed in by subject id

    """

    assert callable(getmethod), "Supplied getmethod is not callable!" \
                                "It must take in a path and return a vectorized feature set and labels."

    # generating an unique numeric label for each class (sorted in order of their appearance in metadata file)
    class_set = set(classes.values())
    class_labels = dict()
    for idx, cls in enumerate(class_set):
        class_labels[cls] = idx

    ids_excluded = list()

    ds = MLDataset()
    for subjid in subjects:
        try:
            data, feat_names = getmethod(featdir, subjid)
            ds.add_sample(subjid, data, class_labels[classes[subjid]], classes[subjid], feat_names)
        except:
            ids_excluded.append(subjid)
            warnings.warn("Features for {} via {} method could not be read. "
                          "Excluding it.".format(subjid, getmethod.__name__))

    # warning for large number of fails for feature extraction
    if len(ids_excluded) > 0:
        warnings.warn('Features for {} subjects could not read. '.format(len(ids_excluded)))
        user_confirmation = raw_input("Would you like to proceed?  y / [N] : ")
        if user_confirmation.lower() not in ['y', 'yes', 'ye']:
            print ('Stopping. \n'
                          'Rerun after completing the feature extraction for all subjects '
                          'or exclude failed subjects..')
            sys.exit(1)
        print(' Proceeding with only {} subjects.'.format(ds.num_samples))

    # save the dataset to disk to enable passing on multiple dataset(s)
    savepath = os.path.join(outdir, outname)
    ds.save(savepath)

    return savepath


def saved_dataset_matches(ds_path, subjects, classes):
    """
    Returns True only if the path to dataset
        exists, is not empy,
        contains the same number of samples,
        same sample ids and classes as in meta data!

    :returns bool.
    """

    if (not os.path.exists(ds_path)) or (os.path.getsize(ds_path) <= 0):
        return False
    else:
        ds = MLDataset(ds_path)
        if set(ds.class_set) != set(classes) or set(ds.sample_ids) != set(subjects):
            return False
        else:
            return True


def visualize_results(results_file_path, outdir, method_names):
    """
    Produces the performance visualizations/comparisons from the cross-validation results.
    
    Parameters
    ----------
    results_file_path
    outdir
    method_names

    """

    dataset_paths, method_names, train_perc, num_repetitions, num_classes, \
        pred_prob_per_class, pred_labels_per_rep_fs, test_labels_per_rep, \
        best_min_leaf_size, best_num_predictors, \
        feature_importances_rf, feature_names, \
        num_times_misclfd, num_times_tested, \
        confusion_matrix, class_order, accuracy_balanced, auc_weighted, positive_class = \
            rhst.load_results(results_file_path)

    if os.environ['DISPLAY'] is None:
        warnings.warn('DISPLAY is not set. Skipping to generate any visualizations.')
        return

    try:
        num_classes = len(method_names)

        balacc_fig_path = os.path.join(outdir, 'balanced_accuracy')
        visualize.metric_distribution(accuracy_balanced, method_names, balacc_fig_path,
                                      num_classes, "Balanced Accuracy")

        confmat_fig_path = os.path.join(outdir, 'confusion_matrix')
        visualize.confusion_matrices(confusion_matrix, class_order, method_names, confmat_fig_path)

        if num_classes > 2:
            cmp_misclf_fig_path = os.path.join(outdir, 'compare_misclf_rates')
            visualize.compare_misclf_pairwise(confusion_matrix, class_order, method_names, cmp_misclf_fig_path)

        featimp_fig_path = os.path.join(outdir, 'feature_importance')
        visualize.feature_importance_map(feature_importances_rf, method_names, featimp_fig_path, feature_names)

        misclf_out_path = os.path.join(outdir, 'misclassified_subjects')
        visualize.freq_hist_misclassifications(num_times_misclfd, num_times_tested, method_names, misclf_out_path)
    except:
        warnings.warn('Error generating the visualizations! Skipping ..')



def export_results(results_file_path, outdir):
    """
    Exports the results to simpler CSV format for use in other packages!
    
    Parameters
    ----------
    results_file_path
    outdir

    Returns
    -------
    None
    
    """

    dataset_paths, method_names, train_perc, num_repetitions, num_classes, \
        pred_prob_per_class, pred_labels_per_rep_fs, test_labels_per_rep, \
        best_min_leaf_size, best_num_predictors, \
        feature_importances_rf, feature_names, \
        num_times_misclfd, num_times_tested, \
        confusion_matrix, class_order, accuracy_balanced, auc_weighted, positive_class = \
            rhst.load_results(results_file_path)

    num_classes = confusion_matrix.shape[0]
    num_rep_cv = confusion_matrix.shape[2]
    num_datasets = confusion_matrix.shape[3]

    # separating CSVs from the PDFs
    exp_dir = os.path.join(outdir, cfg.EXPORT_DIR_NAME)
    if not os.path.exists(exp_dir):
        os.mkdir(exp_dir)

    # TODO think about how to export predictive probability per class per CV rep
    # pred_prob_per_class


    try:
        balacc_path = os.path.join(exp_dir, 'balanced_accuracy.csv')
        np.savetxt(balacc_path, accuracy_balanced,
                   delimiter=cfg.DELIMITER,
                   fmt = cfg.EXPORT_FORMAT,
                   header=','.join(method_names))

        cfmat_reshaped = np.reshape(confusion_matrix, [num_classes*num_classes, num_rep_cv, num_datasets] )
        for mm in range(num_datasets):
            confmat_path = os.path.join(exp_dir, 'confusion_matrix_{}.csv'.format(method_names[mm]))
            np.savetxt(confmat_path,
                       cfmat_reshaped[:,:,mm].T, # NOTICE the transpose
                       delimiter=cfg.DELIMITER, fmt=cfg.EXPORT_FORMAT,
                       comments= 'shape of confusion matrix: num_repetitions x num_classes^2')

        avg_cfmat, misclf_rate = visualize.compute_pairwise_misclf(confusion_matrix)
        num_datasets = misclf_rate.shape[0]
        for mm in range(num_datasets):
            cmp_misclf_path = os.path.join(exp_dir, 'average_misclassification_rates_{}.csv'.format(method_names[mm]))
            np.savetxt(cmp_misclf_path,
                       misclf_rate[mm,:],
                       fmt=cfg.EXPORT_FORMAT, delimiter=cfg.DELIMITER)

        for mm in range(num_datasets):
            featimp_path = os.path.join(exp_dir, 'feature_importance_{}.csv'.format(method_names[mm]))
            np.savetxt(featimp_path,
                       feature_importances_rf[mm],
                       fmt=cfg.EXPORT_FORMAT, delimiter=cfg.DELIMITER,
                       header=','.join(feature_names[mm]))

        perc_misclsfd, _, _, _ = visualize.compute_perc_misclf_per_sample(num_times_misclfd, num_times_tested)
        for mm in range(num_datasets):
            subwise_misclf_path = os.path.join(exp_dir, 'subject_misclf_freq_{}.csv'.format(method_names[mm]))
            # TODO there must be a more elegant way to write dict to CSV
            with open(subwise_misclf_path, 'w') as smf:
                for sid, val in perc_misclsfd[mm].items():
                    smf.write('{}{}{}\n'.format(sid, cfg.DELIMITER, val))

    except:
        raise IOError('Unable to export the results to CSV files.')

    return


def validate_class_set(classes, positiveclass=None):
    ""

    # the following loop is required to preserve original order
    # this does not: class_set_in_meta = list(set(classes.values()))
    class_set_in_meta = list()
    for x in classes.values():
        if x not in class_set_in_meta:
            class_set_in_meta.append(x)

    num_classes = len(class_set_in_meta)
    if num_classes < 2:
        raise ValueError("Atleast two classes are required for predictive analysis! "
                         "Only one given ({})".format(set(classes.values())))

    if num_classes == 2:
        if not_unspecified(positiveclass):
            if positiveclass not in class_set_in_meta:
                raise ValueError('Positive class specified does not exist in meta data.\n'
                                 'Choose one of {}'.format(class_set_in_meta))
            print('Positive class specified for AUC calculation: {}'.format(positiveclass))
        else:
            positiveclass = class_set_in_meta[-1]
            print('Positive class inferred for AUC calculation: {}'.format(positiveclass))

    return positiveclass


def make_dataset_filename(method_name):
    "File name constructor."

    file_name = 'consolidated_{}_{}.MLDataset.pkl'.format(method_name, make_time_stamp())

    return file_name


def import_features(method_list, outdir, subjects, classes, feature_dir):
    """
    Imports the specified features and organizes them into datasets.
     
    Parameters
    ----------
    
    method_list : list of callables
        Set of predefined methods returning a vector of features for a given sample id and location
    outdir : str
        Path to the output folder

    subjects : list of str
        List of sample ids
    classes : dict
        Dict identifying the class for each sample id in the dataset.
    feature_dir : list of str
        List of paths to the root directory containing the features (pre- or user-defined).
        Must be of same length as method_list
        
    Returns
    -------    
    method_names : list of str
        List of method names used for annotation.
    dataset_paths_file : str
        Path to the file containing paths to imported feature sets.
    
    """

    method_names = list()
    outpath_list = list()
    for mm, cur_method in enumerate(method_list):
        if cur_method == userdefinedget:
            method_name = os.path.basename(feature_dir[mm])
        else:
            # adding an index for an even more unique identification
            method_name = '{}_{}'.format(cur_method.__name__,mm)

        method_names.append(method_name)
        out_name = make_dataset_filename(method_name)

        outpath_dataset = os.path.join(outdir, out_name)
        if not saved_dataset_matches(outpath_dataset, subjects, classes):
            # noinspection PyTypeChecker
            outpath_dataset = getfeatures(subjects, classes,
                                          feature_dir[mm],
                                          outdir, out_name,
                                          getmethod = cur_method)

        outpath_list.append(outpath_dataset)

    combined_name = '_'.join(method_names)
    dataset_paths_file = os.path.join(outdir, 'datasetlist.' + combined_name+ '.txt')
    with open(dataset_paths_file, 'w') as dpf:
        dpf.writelines('\n'.join(outpath_list))

    return method_names, dataset_paths_file


def make_method_list(userdir, fsdir):
    """
    Returns an organized list of feature paths and methods to read in features.
    
    Parameters
    ----------
    userdir : list of str
    fsdir : str

    Returns
    -------
    feature_dir : list
    method_list : list
    

    """

    freesurfer_readers = [aseg_stats_subcortical, aseg_stats_whole_brain]

    feature_dir = list()
    method_list = list()
    if not_unspecified(userdir):
        for udir in userdir:
            feature_dir.append(udir)
            method_list.append(userdefinedget)

    if not_unspecified(fsdir):
        for fsrdr in freesurfer_readers:
            feature_dir.append(fsdir)
            method_list.append(fsrdr)

    if len(method_list) != len(feature_dir):
        raise ValueError('Invalid specification for features!')

    if len(method_list) < 1:
        raise ValueError('Atleast one feature set must be specified.')

    print "\nRequested features for analysis:"
    for mm, method in enumerate(method_list):
        print "{} from {}".format(method.__name__, feature_dir[mm])

    return feature_dir, method_list


def run():
    """
    Main entry point.
    
    """

    # TODO design an API interface for advanced access as an importable package

    metadatafile, outdir, userdir, fsdir, train_perc, num_rep_cv, positiveclass = parse_args()

    subjects, classes = get_metadata(metadatafile)

    positiveclass = validate_class_set(classes, positiveclass)

    feature_dir, method_list = make_method_list(userdir, fsdir)

    method_names, dataset_paths_file =  import_features(method_list, outdir, subjects, classes, feature_dir)

    results_file_path = rhst.run(dataset_paths_file, method_names, outdir,
                                 train_perc=train_perc, num_repetitions=num_rep_cv,
                                 positive_class= positiveclass)

    visualize_results(results_file_path, outdir, method_names)

    export_results(results_file_path, outdir)

if __name__ == '__main__':
    run()