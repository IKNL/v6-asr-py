import time
import pandas as pd

from vantage6.common import info  # , error, warning, debug
from vantage6.client import Client


def master(client: Client, data, incidence, population, gender, ageclass,
           prefacture, standard_popultation, organization_ids=None):
    """Master algoritm.

    The master algorithm is the chair of the Round Robin, which makes
    sure everyone waits for their turn to identify themselfs.
    """
    # get all organizations (ids) that are within the collaboration
    # FlaskIO knows the collaboration to which the container belongs
    # as this is encoded in the JWT (Bearer token)
    if not organization_ids:
        organizations = client.get_organizations_in_my_collaboration()
        organization_ids = [organization.get("id") for organization in
                            organizations]

    # all participating paties compute crude rate and incidence population
    info("Dispatching preliminairy_results")
    task_preliminairy_results = client.create_new_task(
        input_={
            "method": "preliminairy_results",
            "kwargs": {
                "incidence": incidence,
                "population": population,
                "gender": gender,
                "ageclass": ageclass,
                "prefacture": prefacture
            }
        },
        organization_ids=organization_ids
    )

    # while we wait, lets compute the relative population dataframe
    info('Calculating relative population')
    rel_pop = relative_population(standard_popultation,
                                  population, ageclass)

    # Collect results
    preliminairy_results = \
        wait_and_collect_results(client, task_preliminairy_results.get('id'))

    crude_rate = [res["crude_rate"] for res in preliminairy_results]
    total_local_pop = \
        [res["total_local_population"] for res in preliminairy_results]
    total_local_incidence = \
        [res["total_local_incidence"] for res in preliminairy_results]
    incidence_population_results = \
        [res["incidence_population"] for res in preliminairy_results]

    info("Combining crude rates")
    crude_rate_combined = \
        combined_crude_rate(total_local_incidence, total_local_pop)

    info("Calculating people at risk")
    people_at_risk_results = people_at_risk(incidence_population_results)

    info("Dispatching Adjusted Rate")
    task_adjusted_rate = client.create_new_task(
        input_={
            "method": "adjusted_rate",
            "kwargs": {
                "incidence": incidence,
                "gender": gender,
                "ageclass": ageclass,
                "rel_pop": rel_pop,
                "people_at_risk": people_at_risk_results,
                "population": population
            }
        },
        organization_ids=organization_ids
    )

    adjusted_rate_results = \
        wait_and_collect_results(client, task_adjusted_rate.get('id'))
    adjusted_rate_glob = \
        [res["adj_rate_glob"] for res in adjusted_rate_results]
    adjusted_rate_local = \
        [res["adj_rate_local"] for res in adjusted_rate_results]

    info("Combining adjusted rates")
    adjusted_rate_combined = combined_adjusted_rate(adjusted_rate_glob)

    info("Master algorithm complete")

    return {
        "local_crude_rate": crude_rate,
        "combined_crude_rate": crude_rate_combined,
        "local_adjusted_rate": adjusted_rate_local,
        "combined_adjusted_rate": adjusted_rate_combined
    }


def wait_and_collect_results(client, task_id):
    task = client.get_task(task_id)
    while not task.get("complete"):
        task = client.get_task(task_id)
        info("Waiting for results")
        time.sleep(1)

    info("Obtaining results")
    results = client.get_results(task_id=task.get("id"))
    return results


def combined_adjusted_rate(adj_rate):
    """Combines the adjusted ASR calculated from RPC_adj_rate

    Parameters
    ----------
    adj_rate : List of series
        list of pd.Series containing the adj_rate per node/region

    Returns
    -------
    pd.core.frame.DataFrame
        Dataframe containing the combined values of the RPC_adj_rate
    """
    return pd.DataFrame(map(sum, zip(*adj_rate)))


def people_at_risk(dataframe_list):
    """Takes in a list of dataframes from RPC_incidence_pop and adds them.

    Parameters
    ----------
    dataframe_list : List
        List of dataframes containing all the people at risk from multiple
        regions/prefactures.

    Returns
    -------
    pd.core.frame.DataFrame
        Dataframe containing all the people at risk in certain regions
    """
    combined_dataframe = dataframe_list[0]
    for dataframe in dataframe_list[1:]:
        combined_dataframe = combined_dataframe.add(dataframe)
    return combined_dataframe


def relative_population(data, population, ageclass):
    """Calculates the relative population used in the Adjusted ASR calculation.
       To do this it first calculates the total population 'total_pop'
       and sums it across the index (row). Then appends a temporary column
       called 'rel_pop' which each value of the standard population divided by
       the total population and multiplied by 100000 so that the total relative
       population now will be 100000 and it is standerdised per age category.

    Parameters
    ----------
    data : pd.DataFrame
        Contains the Standard Population
    population : str
        Population per age category
    ageclass : pd.DataFrame column
        The different age classes
    gender : pd.DataFrame, optional
        This contains the different genders, by default None

    Returns
    -------
    pd.core.frame.DataFrame
        Creates a pivot of the standard population data called realtive_pop
        which is standardised such that the total population is 100000.
    """
    total_pop = data[population].sum(axis=0)
    data['rel_pop'] = (data[population]/total_pop)*100000
    relative_pop = data.pivot(columns=ageclass, values='rel_pop').sum(axis=0)
    return relative_pop


def combined_crude_rate(total_incidence, grouped_populations):
    """As input it takes in the total incidence per node and the corresponding
       population. The method sums the populations into
       one grouped population and calculates the individual crude rate
       per region based off the grouped populations. This is then combined
       into a dataframe.

    Parameters
    ----------
    total_incidence : List
        This is the sum of the incidence per node which is sent from each node
        to the master method. This is grouped in the form of a list.
        This is calculated from the
    grouped_populations : List
        This is the sum of the populations per node which is sent from each
        node to the master method. This is grouped in the form of a list.

    Returns
    -------
    pd.DataFrame
        This is the combined crude rate result from all the participating
        nodes in the algorithm.
    """
    grouped_population = list(map(sum, zip(*grouped_populations)))
    crude = list(map(lambda incidence: (incidence/grouped_population)*100000,
                 total_incidence))
    combined_crude = pd.DataFrame((sum(crude)))
    return combined_crude


def RPC_preliminairy_results(data, incidence, population, gender, ageclass,
                             prefacture=None):
    """Calculates the crude rate as well as preliminary statistics used for
       calculating the combined crude rate.

    Parameters
    ----------
    data : pd.DataFrame
        Pandas Dataframe containing incidencer per age class and gender
    incidence : pd.DataFrame column
        Column containing the incidence (deaths) at each node
    population : pd.DataFrame column
        Column containing the population at each node
    gender : pd.DataFrame column
        Column containing the different genders at each node
    ageclass : pd.DataFrame column
        Column containing the ageclass's at each node
    prefacture : pd.DataFrame column, optional
        Column containing the prefacture, by default None

    Returns
    -------
    Dictionairy
        Returns a dictionairy object containing the crude rate at the node,
        the total number of incidence cases 'incidence pop' by age class and
        gender, summed population 'total_local_pop' at the node (this is
        indifferent of ageclass and gender) as well as the summed incidence
        (this is also indifferent of ageclass and gender)
    """

    if prefacture is not None:

        people_at_risk = data.pivot(
            index=[prefacture, gender],
            columns=ageclass,
            values=population
        ).sum(axis=1)

        incidence_per_prefacture = data.pivot(
            index=[prefacture, gender],
            columns=ageclass,
            values=incidence
        ).sum(axis=1)

        crd_rate = (incidence_per_prefacture.div(people_at_risk))*100000
    else:

        people_at_risk = data.pivot_table(
            index=gender,
            columns=ageclass,
            values=population
        ).sum(axis=1)

        incidence_per_gender_age = data.pivot_table(
            index=gender,
            columns=ageclass,
            values=incidence
        ).sum(axis=1)

        crd_rate = (incidence_per_gender_age.div(people_at_risk))*100000

    incidence_pop = data.pivot(index=gender, columns=ageclass,
                               values=population)
    total_local_pop = incidence_pop.sum(axis=1)

    total_local_inc = data.pivot(index=gender, columns=ageclass,
                                 values=incidence).sum(axis=1)

    return {
        "crude_rate": crd_rate,
        "incidence_population": incidence_pop,
        "total_local_population": total_local_pop,
        "total_local_incidence": total_local_inc
    }


def RPC_adjusted_rate(data, gender, ageclass, incidence, rel_pop,
                      people_at_risk, population):
    """Calculates the adjusted rate for the ASR.
       This does this by first creating a pivot of the local node's data using
       the incidence by age class and gender. Then it is multiplied by rel_pop,
       a dataframe created using the function Relative_population. This is all
       divided by the people at risk which is the total population at risk and
       summed across the columns.

    Parameters
    ----------
    data : pd.DataFrame
        Dataframe containing incidence data per ageclass and gender
    gender : pd.DataFrame column
        The different genders
    ageclass : pd.DataFrame column
        The different age classes
    incidence : pd.DataFrame column
        Column containing the incidence (deaths)
    rel_pop : pd.DataFrame
        Standardised population of 100000
    people_at_risk : pd.DataFrame
        Combined dataframe of all the people at risk of catching the disease
        across all nodes.

    Returns
    -------
    dictionary
        Returns a dictionary object of pd.core.Series containing the adjusted
        rate based on local incidence population and adjusted rate based on
        global population. Depending on how many genders are listed, these will
        be of length len(np.unique(data[gender])).
    """
    incidence_per_ageclass_and_gender = data.pivot(
        index=gender,
        columns=ageclass,
        values=incidence
    )

    adj_rate_glob = incidence_per_ageclass_and_gender.mul(rel_pop).\
        div(people_at_risk).sum(axis=1)

    incidence_pop = data.pivot(index=gender, columns=ageclass,
                               values=population)

    adj_rate_local = incidence_per_ageclass_and_gender.mul(rel_pop).\
        div(incidence_pop).sum(axis=1)

    return {
        "adj_rate_local": adj_rate_local,
        "adj_rate_glob": adj_rate_glob
    }
