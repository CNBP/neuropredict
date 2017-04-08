# neuropredict FAQ

## Frequently Asked Questions

1. What is the overarching goal for neuropredict?
  * To offer a comprehensive report on predictive analysis effortlessly!
  * Aiming to interface directly with the outputs of various neuroimaging tools
    * although the user could input arbitrary set of features (neuroimaging, or otherwise).
2. What is your classification system?
  * Predictive analysis is performed with Random Forest classifier (using scikit-learn's implementation) 
  * Model selection (grid search of optimal hyper parameters) is performed in an inner cross-validation.
3. Why random forests?
  * Because they have consistently demonstrated top performance across multiple domains:
    * Fernández-Delgado, M., Cernadas, E., Barro, S., & Amorim, D. (2014). Do we Need Hundreds of Classifiers to Solve Real World Classification Problems? Journal of Machine Learning Research, 15, 3133–3181.
    * Lebedev, A. V., Westman, E., Van Westen, G. J. P., Kramberger, M. G., Lundervold, A., Aarsland, D., et al. (2014). Random Forest ensembles for detection and prediction of Alzheimer's disease with a good between-cohort robustness. NeuroImage: Clinical, 6, 115–125. http://doi.org/10.1016/j.nicl.2014.08.023
  * Because it's multi-class by design and automatically estimates feature importance.
4. Why no feature selection [yet]?
  * This is a tough question to answer. However, the overarching goals of `neuropredict` might help answer it:
    * to enable novice predictive modeling users to get started easily and quickly,
    * provide a thorough estimate of *baseline* performance of their feature sets, instead of trying to find an arbitrary combination of predictive modeling tools to drive the numerical performance as high as possible.
  * Also because Random forest are supposed to automatically discard features without any useful signal.
  * That said, this is not a permanent choice. `neuropredict` is designed such that another classifier or combination of classifiers could easily be plugged in. Based on user's demand, this might be offered after few initial releases and user testing/feedback.
  
5. Does `neuropredict` handle covariates?
  * No. Not yet. This feature request is not trivial to implement, as the nature of covariate handling is complex and variety of methods is large.
  * If you need to, please regress them out (or handle them using another method of your choice) prior to inputting the features.
  
6. Can I compare an arbitrary set of my own custom-designed features?
  * Yes. The -u option allows you to supply arbitrary set of paths to user's own custom features e.g. `-u /myproject/awsome-new-idea-v2.0 /myproject/awsome-new-idea-v1 /myproject/DTI_FA_Method1 /myproject/resting-dynamic-fc /prevproject/resting-dynamic-fc-competingmethod`
  
7. Can I combine `-f` option with `-u` to compare my own features with that of Freesurfer or other supported software?
  * Absolutely. 
  * While `-f` option allows specifying only 1 freesurfer folder, it can be combined with `-u` which can take arbitray number of custom features.

7. Can I get ROC curves?
  * Not at the moment, as the presented results and report is obtained from a large number of CV iterations and there is not one ROC curve to represent it all.
  * It is indeed possible to *"average"* ROC curves from multiple iterations (see below) and visualize it. This feature will be added soon.
    * Fawcett, T. (2006). An introduction to ROC analysis. Pattern Recognition Letters, 27(8), 861–874.
  
   
