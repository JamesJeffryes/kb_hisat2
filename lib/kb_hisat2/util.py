"""
Some utility functions for the HISAT2 module.
These mainly deal with manipulating files from Workspace objects.
There's also some parameter checking and munging functions.
"""
from __future__ import print_function
from pprint import pprint
from Workspace.WorkspaceClient import Workspace
from AssemblyUtil.AssemblyUtilClient import AssemblyUtil
from ReadsUtils.ReadsUtilsClient import ReadsUtils
from SetAPI.SetAPIClient import SetAPI


def check_hisat2_parameters(params):
    """
    Checks to ensure that the hisat2 parameter set is correct and has the right
    mash of options.
    Returns a list of error strings if there's a problem, or just an empty list otherwise.
    """
    errors = list()
    return errors


def setup_hisat2():
    pass


def fetch_fasta_from_genome(genome_ref, ws_url, callback_url):
    """
    Returns an assembly or contigset as FASTA.
    """
    if not check_ref_type(genome_ref, ['KBaseGenomes.Genome'], ws_url):
        raise ValueError("The given genome_ref {} is not a KBaseGenomes.Genome type!")
    # test if genome references an assembly type
    # do get_objects2 without data. get list of refs
    ws = Workspace(ws_url)
    genome_obj_info = ws.get_objects2({
        'objects': [{'ref': genome_ref}],
        'no_data': 1
    })
    # get the list of genome refs from the returned info.
    # if there are no refs (or something funky with the return), this will be an empty list.
    # this WILL fail if data is an empty list. But it shouldn't be, and we know because
    # we have a real genome reference, or get_objects2 would fail.
    genome_obj_refs = genome_obj_info.get('data', [{}])[0].get('refs', [])

    # see which of those are of an appropriate type (ContigSet or Assembly), if any.
    assembly_ref = list()
    ref_params = [{'ref': x} for x in genome_obj_refs]
    ref_info = ws.get_object_info3({'objects': ref_params})
    for idx, info in enumerate(ref_info.get('infos')):
        if "KBaseGenomeAnnotations.Assembly" in info[2] or "KBaseGenomes.ContigSet" in info[2]:
            assembly_ref.append(";".join(ref_info.get('paths')[idx]))

    if len(assembly_ref) == 1:
        return fetch_fasta_from_assembly(assembly_ref[0], ws_url, callback_url)
    else:
        raise ValueError("Multiple assemblies found associated with the given genome ref {}! "
                         "Unable to continue.")


def fetch_fasta_from_assembly(assembly_ref, ws_url, callback_url):
    """
    From an assembly or contigset, this uses a data file util to build a FASTA file and return the
    path to it.
    """
    allowed_types = ['KBaseFile.Assembly',
                     'KBaseGenomeAnnotations.Assembly',
                     'KBaseGenomes.ContigSet']
    if not check_ref_type(assembly_ref, allowed_types, ws_url):
        raise ValueError("The reference {} cannot be used to fetch a FASTA file".format(
            assembly_ref))
    au = AssemblyUtil(callback_url)
    return au.get_assembly_as_fasta({'ref': assembly_ref})


def fetch_fasta_from_object(ref, ws_url, callback_url):
    """
    From the object given in ref, if it's either a KBaseGenomes.Genome or a
    KBaseGenomeAnnotations.Assembly, or a KBaseGenomes.ContigSet, this will download and return
    the path to a FASTA file made from its sequence.
    """
    obj_type = get_object_type(ref, ws_url)
    if "KBaseGenomes.Genome" in obj_type:
        return fetch_fasta_from_genome(ref, ws_url, callback_url)
    elif "KBaseGenomeAnnotations.Assembly" in obj_type or "KBaseGenomes.ContigSet" in obj_type:
        return fetch_fasta_from_assembly(ref, ws_url, callback_url)
    else:
        raise ValueError("Unable to fetch a FASTA file from an object of type {}".format(obj_type))


def fetch_reads_refs_from_sampleset(ref, ws_url, callback_url):
    """
    From the given object ref, return a list of all reads objects that are a part of that
    object. E.g., if ref is a ReadsSet, return a list of all PairedEndLibrary or SingleEndLibrary
    refs that are a member of that ReadsSet.

    If ref is already a Reads library, just returns a list with ref as a single element.
    """
    obj_type = get_object_type(ref, ws_url)
    refs = list()
    if "KBaseSets.ReadsSet" in obj_type:
        print("Looking up reads references in ReadsSet object")
        set_client = SetAPI(callback_url)
        reads_set = set_client.get_reads_set_v1({
            "ref": ref,
            "include_item_info": 0
        })
        for reads in reads_set["data"]["items"]:
            refs.append(reads["ref"])
    elif "KBaseRNASeq.RNASeqSampleSet" in obj_type:
        print("Looking up reads references in RNASeqSampleSet object")
        ws = Workspace(ws_url)
        sample_set = ws.get_objects2({"objects": [{"ref": ref}]})["data"][0]["data"]
        refs = sample_set["sample_ids"]
    elif ("KBaseAssembly.SingleEndLibrary" in obj_type or
          "KBaseFile.SingleEndLibrary" in obj_type or
          "KBaseAssembly.PairedEndLibrary" in obj_type or
          "KBaseFile.PairedEndLibrary" in obj_type):
        refs.append(ref)
    else:
        raise ValueError("Unable to fetch reads reference from object {} "
                         "which is a {}".format(ref, obj_type))

    return refs


def fetch_reads_from_reference(ref, callback_url):
    """
    Fetch a FASTQ file (or 2 for paired-end) from a reads reference.
    Returns the following structure:
    {
        "style": "paired", "single", or "interleaved",
        "file_fwd": path_to_file,
        "file_rev": path_to_file, only if paired end,
        "object_ref": reads reference for downstream convenience.
    }
    """
    try:
        print("Fetching reads from object {}".format(ref))
        reads_client = ReadsUtils(callback_url)
        reads_dl = reads_client.download_reads({"read_libraries": [ref]})
        pprint(reads_dl)
        reads_files = reads_dl['files'][ref]['files']
        ret_reads = {
            "object_ref": ref,
            "style": reads_files["type"],
            "file_fwd": reads_files["fwd"],
        }
        if reads_files.get("rev", None) is not None:
            ret_reads["file_rev"] = reads_files["rev"]
        return ret_reads
    except:
        print("Unable to fetch a file from expected reads object {}".format(ref))
        raise


def check_ref_type(ref, allowed_types, ws_url):
    """
    Validates the object type of ref against the list of allowed types. If it passes, this
    returns True, otherwise False.
    Really, all this does is verify that at least one of the strings in allowed_types is
    a substring of the ref object type name.
    Ex1:
    ref = "KBaseGenomes.Genome-4.0"
    allowed_types = ["assembly", "KBaseFile.Assembly"]
    returns False
    Ex2:
    ref = "KBaseGenomes.Genome-4.0"
    allowed_types = ["assembly", "genome"]
    returns True
    """
    obj_type = get_object_type(ref, ws_url).lower()
    for t in allowed_types:
        if t.lower() in obj_type:
            return True
    return False


def get_object_type(ref, ws_url):
    """
    Fetches and returns the typed object name of ref from the given workspace url.
    If that object doesn't exist, or there's another Workspace error, this raises a
    RuntimeError exception.
    """
    ws = Workspace(ws_url)
    info = ws.get_object_info3({'objects': [{'ref': ref}]})
    obj_info = info.get('infos', [[]])[0]
    if len(obj_info) == 0:
        raise RuntimeError("An error occurred while fetching type info from the Workspace. "
                           "No information returned for reference {}".format(ref))
    return obj_info[2]
