# Vibe - Music Recommendation System
### Find music that you'll vibe with!

Final project for the McGill AI Society's Accelerated Introduction to Machine Learning Bootcamp (Fall 2023). 
Original dataset of songs retrieved from [Kaggle](https://www.kaggle.com/datasets/amitanshjoshi/spotify-1million-tracks/).

## Description

Vibe is a content-based music recommendation system with a dataset of over fifty thousand unique artists and a million songs released between 2000 and 2023. The system can handle both artists and specific songs as input; recommendations are generated using SciPy's cdist method by selecting the songs in the dataset with the smallest Euclidean distance from the given input.

## Using the app

Vibe is hosted and available online on [Streamlit](https://vibemusic.streamlit.app) and [Hugging Face](https://huggingface.co/spaces/Al3x-T/Vibe).

To run the app locally, install the packages in requirements.txt and and run

```
streamlit run app/streamlit_app_local.py
```

## Repository organization

1. app/
	* files for the Streamlit application
2. data/
	* process_data.ipynb: file used to process the data.csv obtained from Kaggle and save it as a Parquet file
    * data_encoded.parquet: processed data used by the Streamlit application to generate recommendations
3. MAIS 202/
	* deliverables submitted to the MAIS 202 bootcamp
