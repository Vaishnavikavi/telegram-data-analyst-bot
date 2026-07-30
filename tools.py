import os
import json
import pandas as pd
import requests

from io import BytesIO


TEMP_DIR = "temp"

os.makedirs(
    TEMP_DIR,
    exist_ok=True
)



def download_file(url):

    response = requests.get(
        url,
        timeout=60
    )

    response.raise_for_status()


    filename = url.split("/")[-1]


    if "." not in filename:
        filename = "dataset.csv"


    path = os.path.join(
        TEMP_DIR,
        filename
    )


    with open(
        path,
        "wb"
    ) as f:

        f.write(
            response.content
        )


    return path




def load_dataset(path):

    extension = (
        path
        .lower()
        .split(".")[-1]
    )


    if extension in [
        "csv",
        "txt"
    ]:

        return pd.read_csv(
            path
        )


    if extension in [
        "xlsx",
        "xls"
    ]:

        return pd.read_excel(
            path
        )


    if extension == "json":

        return pd.read_json(
            path
        )


    raise Exception(
        f"Unsupported file type: {extension}"
    )




def dataframe_summary(df):

    summary = {}


    summary["rows"] = int(
        len(df)
    )


    summary["columns"] = list(
        df.columns
    )


    summary["column_types"] = {
        col:
        str(dtype)
        for col, dtype
        in df.dtypes.items()
    }



    summary["missing_values"] = {
        col:
        int(value)
        for col, value
        in df.isna()
        .sum()
        .items()
    }



    numerical = (
        df
        .select_dtypes(
            include="number"
        )
    )


    if len(numerical.columns):

        summary["numeric_summary"] = (
            numerical
            .describe()
            .round(3)
            .to_dict()
        )


    categorical = (
        df
        .select_dtypes(
            include="object"
        )
    )


    categories = {}


    for col in categorical.columns:

        categories[col] = (
            df[col]
            .value_counts()
            .head(10)
            .to_dict()
        )


    summary["categorical_summary"] = categories



    return summary




def analyze_dataset(
        url,
        question
):

    path = download_file(
        url
    )


    df = load_dataset(
        path
    )


    summary = dataframe_summary(
        df
    )


    #
    # Give Gemini a sample
    #

    sample = (
        df
        .head(5)
        .to_dict(
            orient="records"
        )
    )


    result = {

        "question":
            question,

        "dataset_file":
            path,

        "summary":
            summary,

        "sample_rows":
            sample

    }


    return result
