import os
import pandas as pd
import requests


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


        #
        # Numeric columns
        #

        if pd.api.types.is_numeric_dtype(df[col]):


            info["min"] = float(
                df[col].min()
            )

            info["max"] = float(
                df[col].max()
            )

            info["mean"] = float(
                df[col].mean()
            )

            info["median"] = float(
                df[col].median()
            )

            info["std"] = float(
                df[col].std()
            )


        #
        # Try converting object columns
        #

        else:

            converted = pd.to_numeric(
                df[col],
                errors="coerce"
            )


            if converted.notna().sum() > 0.8 * len(df):

                info["dtype"] = "numeric"

                info["min"] = float(
                    converted.min()
                )

                info["max"] = float(
                    converted.max()
                )

                info["mean"] = float(
                    converted.mean()
                )

                info["median"] = float(
                    converted.median()
                )


            else:

                info["unique_values"] = (
                    df[col]
                    .dropna()
                    .astype(str)
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


        result[col] = info


    return result



def important_calculations(df):

    output = {}


    numeric_cols = [
        col
        for col in df.columns
        if pd.api.types.is_numeric_dtype(df[col])
    ]


    output["numeric_columns"] = numeric_cols



    #
    # Correlations
    #

    if len(numeric_cols) > 1:

        output["correlation"] = (
            df[numeric_cols]
            .corr()
            .round(3)
            .to_dict()
        )



    #
    # Group analysis
    #

    categorical_cols = [
        col
        for col in df.columns
        if (
            df[col].dtype == "object"
            or str(df[col].dtype).startswith("category")
        )
    ]


    groups = {}


    for cat in categorical_cols:


        if df[cat].nunique() <= 100:


            for num in numeric_cols:


                try:

                    groups[
                        f"{cat}_average_{num}"
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


                except Exception:

                    continue



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

        "rows": int(
            len(df)
        ),

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
