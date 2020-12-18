<h1 align="center">
  <br>
  <a href="https://vantage6.ai"><img src="https://github.com/IKNL/guidelines/blob/master/resources/logos/vantage6.png?raw=true" alt="vantage6" width="400"></a>
</h1>

<h3 align=center> A privacy preserving federated learning solution</h3>

--------------------

# Age Standerdized Incidence Rate
|:warning: priVAcy preserviNg federaTed leArninG infrastructurE for Secure Insight eXchange (VANTAGE6) |
|------------------|
| This algorithm is part of [VANTAGE6](https://github.com/IKNL/vantage6). A docker build of this algorithm can be obtained from harbor.vantage6.ai/algorithms/asr |

It reports the `local_crude_rate`, `combined_crude_rate`, `local_adjusted_rate` and `combined_adjusted_rate` from each `Node`.

## Possible Privacy Issues

🚨 Column names can be geussed, by trail and error

## Privacy Protection

✔️ If column names do not match nothing is reported <br />
✔️ If dataset has less that 10 columns, no statistical analysis is performed <br />
✔️ Only statistical results in the form of aggregated data `local_crude_rate`, `global_crude_rate`, `local_adjusted_rate` and `global_adjusted_rate`
are reported

## Usage
```python
from vantage6.client import Client
from pathlib import Path
import pandas as pd

# Create, athenticate and setup client
client = Client("http://127.0.0.1", 5000, "/api")
client.authenticate("hasan@iknl.nl", "password")
client.setup_encryption(None)

# Define algorithm input
input_ = {
        "method": "master",
        "master": True,
        "kwargs": {
            "incidence": "incidence",
            "population": "pop",
            "gender": "sex",
            "ageclass": "agec",
            "prefacture": "pref",
            "standard_popultation": pd.read_excel('/path/to/file')
        }
    }

# Send the task to the central server
task = client.post_task(
    name="testing",
    image="harbor.vantage6.ai/algorithms/asr",
    collaboration_id=1,
    input_= input_,
    organization_ids=[1]
)

# Retrieve the results
res = client.get_results(task_id=task.get("id"))
