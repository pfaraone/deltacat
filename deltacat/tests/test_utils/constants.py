import json
from deltacat.storage import Delta

test_delta_file = open("deltacat/tests/test_utils/resources/test_delta.json")
test_delta_dict = json.load(test_delta_file)
TEST_UPSERT_DELTA = Delta(test_delta_dict)

test_delete_delta_file = open(
    "deltacat/tests/test_utils/resources/test_delete_delta.json"
)
test_delete_delta_dict = json.load(test_delete_delta_file)

TEST_DELETE_DELTA = Delta(test_delete_delta_dict)
