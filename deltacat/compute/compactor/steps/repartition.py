import importlib
import logging
from contextlib import nullcontext
import pyarrow.compute as pc
import pyarrow as pa
from typing import List, Optional
from deltacat.types.media import StorageType, ContentType
import ray
from deltacat import logs
from deltacat.compute.compactor import DeltaAnnotated
from deltacat.compute.compactor.model.repartition_result import RepartitionResult
from deltacat.storage import interface as unimplemented_deltacat_storage
from deltacat.storage import Partition
from deltacat.utils.ray_utils.runtime import (
    get_current_ray_task_id,
    get_current_ray_worker_id,
)
from deltacat.utils.common import ReadKwargsProvider
from deltacat.utils.performance import timed_invocation
from deltacat.utils.metrics import emit_timer_metrics, MetricsConfig
from deltacat.storage import Delta
from enum import Enum

if importlib.util.find_spec("memray"):
    import memray

logger = logs.configure_deltacat_logger(logging.getLogger(__name__))

# Similar to Spark (https://sparkbyexamples.com/spark/spark-partitioning-understanding/), where
# partition helps in localizing the data and reduce the data shuffling across the network nodes reducing network latency
# which is a major component of the transformation operation thereby reducing the time of completion.
# Deltacat with Ray can support different partitioning strategies to reduce the data movement either across network or between compute and storage
# Note that the term partition here is different from the term used in catalog
# Type of Partition:
# Range Partition: It assigns rows to partitions based on column values falling within a given range, e.g., repartition(column="last_updated", ranges=['2023-01-01', '2023-02-01', '2023-03-01']), data will be split into 4 files
# Hash Partition: Hash Partitioning attempts to spread the data evenly across various partitions based on the key, e.g., repartition(column="last_updated", num_partitions=10), data will be split into 10 files evenly


class RepartitionType(str, Enum):
    RANGE = "range"
    HASH = "hash"


def _timed_repartition(
    annotated_delta: DeltaAnnotated,
    repartition_type: RepartitionType,
    repartition_args: dict,
    destination_partition: Partition,
    enable_profiler: bool,
    read_kwargs_provider: Optional[ReadKwargsProvider],
    repartitioned_file_content_type: ContentType = ContentType.PARQUET,
    deltacat_storage=unimplemented_deltacat_storage,
) -> RepartitionResult:

    if repartition_type == RepartitionType.RANGE:
        column: str = repartition_args["column"]
        partition_ranges: List = repartition_args["ranges"]
        task_id = get_current_ray_task_id()
        worker_id = get_current_ray_worker_id()
        with memray.Tracker(
            f"repartition_{worker_id}_{task_id}.bin"
        ) if enable_profiler else nullcontext():
            tables: List[pa.Table] = deltacat_storage.download_delta(
                annotated_delta,
                storage_type=StorageType.LOCAL,
                file_reader_kwargs_provider=read_kwargs_provider,
            )
            # check if the column exists in the table
            if not all(column in table.column_names for table in tables):
                raise ValueError(f"Column {column} does not exist in the table")
            # given a range [x, y, z], we need to split the table into 4 files, i.e., (-inf, x], (x, y], (y, z], (z, inf)
            partitioned_tables_list = [[] for _ in range(len(partition_ranges) + 1)]
            total_record_count = 0
            col_name_int64 = f"{column}_int64"
            for table in tables:
                total_record_count += len(table)
                table_new = table.add_column(
                    0,
                    pa.field(col_name_int64, pa.int64()),
                    pc.cast(table[column], pa.int64()),
                )
                # handle the partition for values less than or equal to the smallest value
                partitioned_tables_list[0].append(
                    table_new.filter(
                        pc.field(col_name_int64) <= pc.scalar(partition_ranges[0])
                    )
                )
                # Iterate over pairs of values in partition_ranges
                for i, (lower_limit, upper_limit) in enumerate(
                    zip(partition_ranges[:-1], partition_ranges[1:]), start=1
                ):
                    # Add the table filtered by the lower and upper limits to partitioned_tables
                    partitioned_tables_list[i].append(
                        table_new.filter(
                            (pc.field(col_name_int64) > pc.scalar(lower_limit))
                            & (pc.field(col_name_int64) <= pc.scalar(upper_limit))
                        )
                    )
                # handle the partition for values greater than the largest value
                partitioned_tables_list[-1].append(
                    table_new.filter(
                        pc.field(col_name_int64) > pc.scalar(partition_ranges[-1])
                    )
                )

            # TODO(rootliu) set optimal or max number of records per file to defer the performance degradation due to too many small files
            partition_table_length = 0
            # After re-grouping the tables by specified ranges, for each group, we need concat and stage the tables
            partition_deltas: List[Delta] = []
            for partition_tables in partitioned_tables_list:
                if len(partition_tables) > 0:
                    partition_table = pa.concat_tables(partition_tables)
                    if len(partition_table) > 0:
                        partition_table_length += len(partition_table)
                        partition_delta = deltacat_storage.stage_delta(
                            partition_table,
                            destination_partition,
                            content_type=repartitioned_file_content_type,
                        )
                        partition_deltas.append(partition_delta)

            assert (
                partition_table_length == total_record_count
            ), f"Repartitioned table should have the same number of records {partition_table_length} as the original table {total_record_count}"
            return RepartitionResult(
                range_deltas=partition_deltas,
            )
    else:
        raise NotImplementedError(
            f"Repartition type {repartition_type} is not supported."
        )


@ray.remote
def repartition(
    annotated_delta: DeltaAnnotated,
    destination_partition: Partition,
    repartition_type: RepartitionType,
    repartition_args: dict,
    enable_profiler: bool,
    metrics_config: Optional[MetricsConfig],
    read_kwargs_provider: Optional[ReadKwargsProvider],
    repartitioned_file_content_type: ContentType = ContentType.PARQUET,
    deltacat_storage=unimplemented_deltacat_storage,
) -> RepartitionResult:
    logger.info(f"Starting repartition task...")
    repartition_result, duration = timed_invocation(
        func=_timed_repartition,
        annotated_delta=annotated_delta,
        repartition_type=repartition_type,
        repartition_args=repartition_args,
        destination_partition=destination_partition,
        enable_profiler=enable_profiler,
        read_kwargs_provider=read_kwargs_provider,
        repartitioned_file_content_type=repartitioned_file_content_type,
        deltacat_storage=deltacat_storage,
    )
    if metrics_config:
        emit_timer_metrics(
            metrics_name="repartition", value=duration, metrics_config=metrics_config
        )
    return repartition_result
