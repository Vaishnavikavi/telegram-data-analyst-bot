import os
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

    ext = path.lower().split(".")[-1]


    if ext == "csv":
        return pd.read_csv(path)


    if ext in ["xls", "xlsx"]:
        return pd.read_excel(path)


    if ext == "json":
        return pd.read_json(path)


    raise Exception(
        "Unsupported file format"
    )



def analyze_columns(df):

    result = {}


    for col in df.columns:

        info = {}

        info["dtype"] = str(
            df[col].dtype
        )

        info["missing"] = int(
            df[col].isna().sum()
        )


        if df[col].dtype == "object":

            info["unique_values"] = (
                df[col]
                .dropna()
                .unique()
                [:20]
                .tolist()
            )


            info["top_values"] = (
                df[col]
                .value_counts()
                .head(10)
                .to_dict()
            )


        else:

            info["min"] = float(
                df[col].min()
            )

            info["max"] = float(
                df[col].max()
            )

            info["mean"] = float(
                df[col].mean()
            )


        result[col] = info


    return result



def important_calculations(df):

    output = {}


    numeric_cols = (
        df
        .select_dtypes(
            include="number"
        )
        .columns
        .tolist()
    )


    output["numeric_columns"] = numeric_cols



    #
    # Correlation
    #

    if len(numeric_cols) > 1:

        output["correlation"] = (
            df[numeric_cols]
            .corr()
            .round(3)
            .to_dict()
        )



    #
    # Top values for categorical columns
    #

    categorical_cols = (
        df
        .select_dtypes(
            include="object"
        )
        .columns
        .tolist()
    )


    groups = {}


    for cat in categorical_cols:


        if len(df[cat].unique()) < 100:


            for num in numeric_cols:


                try:

                    groups[
                        f"{cat}_by_{num}"
                    ] = (
                        df
                        .groupby(cat)[num]
                        .mean()
                        .sort_values(
                            ascending=False
                        )
                        .head(10)
                        .to_dict()
                    )


                except:

                    pass


    output["group_analysis"] = groups


    return output



def analyze_dataset(url, question):


    path = download_file(
        url
    )


    df = load_dataset(
        path
    )


    result = {

        "question": question,

        "rows": len(df),

        "columns": list(
            df.columns
        ),

        "column_analysis":
            analyze_columns(df),

        "calculations":
            important_calculations(df),

        "sample_rows":
            df.head(10)
            .to_dict(
                orient="records"
            )
    }


    return result
