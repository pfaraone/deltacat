import pytest

# import pyarrow as pa

from deltacat.storage import DeltaType
from deltacat.compute.compactor import (
    DeltaAnnotated,
)
from deltacat.storage import (
    Partition,
    PartitionLocator,
    Stream,
)
from deltacat.tests.compute.test_util_constant import (
    TEST_S3_RCF_BUCKET_NAME,
)
from deltacat.tests.compute.test_util_common import (
    create_src_table,
    create_destination_table,
)

from deltacat.utils.rangedictionary import IntegerRangeDict

from dataclasses import dataclass, fields
import ray
import os
from typing import Any, Dict, List, Optional, Tuple
import deltacat.tests.local_deltacat_storage as ds
from deltacat.compute.compactor.model.compact_partition_params import (
    CompactPartitionParams,
)
import pyarrow as pa


DATABASE_FILE_PATH_KEY, DATABASE_FILE_PATH_VALUE = (
    "db_file_path",
    "deltacat/tests/local_deltacat_storage/db_test.sqlite",
)


@dataclass(frozen=True)
class PrepareDeleteTestCaseParams:
    """
    A pytest parameterized test case for the `prepare_deletes` function.
    """

    deltas_to_compact: List[Tuple[pa.Table, DeltaType, Optional[Dict[str, str]]]]
    deletes_to_apply_obj_ref_by_stream_position: IntegerRangeDict
    expected_dictionary_length: int
    expected_delete_table: List[pa.Table]

    # makes TestCaseParams iterable which is required to build the list of pytest.param values to pass to pytest.mark.parametrize
    def __iter__(self):
        return (getattr(self, field.name) for field in fields(self))


@pytest.fixture(autouse=True, scope="module")
def setup_ray_cluster():
    ray.init(local_mode=True, ignore_reinit_error=True)
    yield


@pytest.fixture(scope="function")
def local_deltacat_storage_kwargs(request: pytest.FixtureRequest):
    # see deltacat/tests/local_deltacat_storage/README.md for documentation
    kwargs_for_local_deltacat_storage: Dict[str, Any] = {
        DATABASE_FILE_PATH_KEY: DATABASE_FILE_PATH_VALUE,
    }
    yield kwargs_for_local_deltacat_storage
    if os.path.exists(DATABASE_FILE_PATH_VALUE):
        os.remove(DATABASE_FILE_PATH_VALUE)


TEST_CASES_PREPARE_DELETE = {
    "1-test-single-upsert": PrepareDeleteTestCaseParams(
        [
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(20, 30)]),
                        pa.array(["foo"] * 10),
                        pa.array([i / 10 for i in range(40, 50)]),
                    ],
                    names=["pk_col_1", "sk_col_1", "sk_col_2", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
        ],
        IntegerRangeDict(),
        0,
        None,
    ),
    "2-test-single-upsert-then-delete": PrepareDeleteTestCaseParams(
        [
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(20, 30)]),
                        pa.array(["foo"] * 10),
                        pa.array([i for i in range(40, 50)]),
                    ],
                    names=["pk_col_1", "sk_col_1", "sk_col_2", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([40]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
        ],
        IntegerRangeDict(),
        1,
        [
            pa.Table.from_arrays(
                [
                    pa.array([40]),
                ],
                names=["col_1"],
            )
        ],
    ),
    "3-test-upsert-delete-upsert": PrepareDeleteTestCaseParams(
        [
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(40, 50)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([40]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(70, 80)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
        ],
        IntegerRangeDict(),
        1,
        [
            pa.Table.from_arrays(
                [
                    pa.array([40]),
                ],
                names=["col_1"],
            )
        ],
    ),
    "4-test-upsert-delete-upsert-delete": PrepareDeleteTestCaseParams(
        [
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(40, 50)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([40]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(70, 80)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([72]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
        ],
        IntegerRangeDict(),
        2,
        [
            pa.Table.from_arrays(
                [
                    pa.array([40]),
                ],
                names=["col_1"],
            ),
            pa.Table.from_arrays(
                [
                    pa.array([72]),
                ],
                names=["col_1"],
            ),
        ],
    ),
    "5-test-upsert-deletesequence-upsert-delete": PrepareDeleteTestCaseParams(
        [
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(40, 50)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([40]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([41]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([42]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([str(i) for i in range(10)]),
                        pa.array([i for i in range(70, 80)]),
                    ],
                    names=["pk_col_1", "col_1"],
                ),
                DeltaType.UPSERT,
                None,
            ),
            (
                pa.Table.from_arrays(
                    [
                        pa.array([72]),
                    ],
                    names=["col_1"],
                ),
                DeltaType.DELETE,
                {"DELETE_COLUMNS": ["col_1"]},
            ),
        ],
        IntegerRangeDict(),
        2,
        [
            pa.Table.from_arrays(
                [
                    pa.array([40, 41, 42]),
                ],
                names=["col_1"],
            ),
            pa.Table.from_arrays(
                [
                    pa.array([72]),
                ],
                names=["col_1"],
            ),
        ],
    ),
}


class TestPrepareDeletes:
    @pytest.mark.parametrize(
        [
            "test_name",
            "deltas_to_compact",
            "deletes_to_apply_obj_ref_by_stream_position",
            "expected_dictionary_length",
            "expected_delete_tables",
        ],
        [
            (
                test_name,
                deltas_to_compact,
                deletes_to_apply_obj_ref_by_stream_position,
                expected_dictionary_length,
                expected_delete_tables,
            )
            for test_name, (
                deltas_to_compact,
                deletes_to_apply_obj_ref_by_stream_position,
                expected_dictionary_length,
                expected_delete_tables,
            ) in TEST_CASES_PREPARE_DELETE.items()
        ],
        ids=[test_name for test_name in TEST_CASES_PREPARE_DELETE],
    )
    def test_prepare_deletes_with_deletes(
        self,
        local_deltacat_storage_kwargs: Dict[str, Any],
        test_name,
        deltas_to_compact,
        deletes_to_apply_obj_ref_by_stream_position,
        expected_dictionary_length,
        expected_delete_tables,
    ):
        from deltacat.compute.compactor_v2.deletes.prepare_deletes import (
            prepare_deletes,
        )

        ray.shutdown()
        ray.init(local_mode=True, ignore_reinit_error=True)
        source_namespace, source_table_name, source_table_version = create_src_table(
            set(["pk_1"]),
            None,
            None,
            local_deltacat_storage_kwargs,
        )
        source_table_stream: Stream = ds.get_stream(
            namespace=source_namespace,
            table_name=source_table_name,
            table_version=source_table_version,
            **local_deltacat_storage_kwargs,
        )
        staged_partition: Partition = ds.stage_partition(
            source_table_stream, None, **local_deltacat_storage_kwargs
        )
        input_deltas = []
        for (incremental_delta, delta_type, delta_properties) in deltas_to_compact:
            input_deltas.append(
                ds.commit_delta(
                    ds.stage_delta(
                        incremental_delta,
                        staged_partition,
                        delta_type,
                        properties=delta_properties if not None else {},
                        **local_deltacat_storage_kwargs,
                    ),
                    **local_deltacat_storage_kwargs,
                )
            )
        ds.commit_partition(staged_partition, **local_deltacat_storage_kwargs)
        src_table_stream_after_committed_delta: Stream = ds.get_stream(
            source_namespace,
            source_table_name,
            source_table_version,
            **local_deltacat_storage_kwargs,
        )
        src_partition_after_committed_delta: Partition = ds.get_partition(
            src_table_stream_after_committed_delta.locator,
            None,
            **local_deltacat_storage_kwargs,
        )
        (
            destination_table_namespace,
            destination_table_name,
            destination_table_version,
        ) = create_destination_table(
            set(["pk_1"]),
            None,
            None,
            local_deltacat_storage_kwargs,
        )
        destination_table_stream: Stream = ds.get_stream(
            namespace=destination_table_namespace,
            table_name=destination_table_name,
            table_version=destination_table_version,
            **local_deltacat_storage_kwargs,
        )
        params = CompactPartitionParams.of(
            {
                "compaction_artifact_s3_bucket": TEST_S3_RCF_BUCKET_NAME,
                "deltacat_storage": ds,
                "deltacat_storage_kwargs": local_deltacat_storage_kwargs,
                "destination_partition_locator": PartitionLocator.of(
                    destination_table_stream, None, None
                ),
                "last_stream_position_to_compact": staged_partition.stream_position,
                "list_deltas_kwargs": {
                    **local_deltacat_storage_kwargs,
                    **{"equivalent_table_types": []},
                },
                "read_kwargs_provider": None,
                "source_partition_locator": src_partition_after_committed_delta.locator,
            }
        )
        deltas_annotated = [DeltaAnnotated.of(delta) for delta in input_deltas]
        actual_deletes_to_apply_by_spos = prepare_deletes(
            params,
            deltas_annotated,
            deletes_to_apply_obj_ref_by_stream_position,
        )
        actual_dictionary_length = len(actual_deletes_to_apply_by_spos)
        assert (
            expected_dictionary_length == actual_dictionary_length
        ), f"{expected_dictionary_length} does not match {actual_dictionary_length}"
        if expected_dictionary_length > 0:
            actual_tables = [
                ray.get(obj_ref)
                for _, obj_ref in actual_deletes_to_apply_by_spos.items()
            ]
            for i, actual_table in enumerate(actual_tables):
                assert actual_table.equals(expected_delete_tables[i])
        return