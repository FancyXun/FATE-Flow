#
#  Copyright 2019 The FATE Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import argparse
import os
import sys
import traceback
from fate_arch.common import file_utils
from fate_arch.common.base_utils import current_timestamp
from fate_arch.common.log import schedule_logger, getLogger
from fate_flow.component_env_utils import provider_utils
from fate_flow.controller.task_controller import TaskController
from fate_flow.entity.types import ProcessRole
from fate_flow.entity.component_provider import ComponentProvider
from fate_flow.db.runtime_config import RuntimeConfig
from fate_flow.utils import schedule_utils
from fate_flow.db.component_registry import ComponentRegistry
from fate_flow.manager.provider_manager import ProviderManager

LOGGER = getLogger()


class TaskInitializer(object):
    @classmethod
    def run(cls):
        result = {}
        try:
            parser = argparse.ArgumentParser()
            parser.add_argument("-j", "--job_id", required=True, type=str, help="job id")
            parser.add_argument("-r", "--role", required=True, type=str, help="role")
            parser.add_argument("-p", "--party_id", required=True, type=int, help="party id")
            parser.add_argument("-c", "--config", required=True, type=str, help="parameters")
            parser.add_argument("--result", required=True, type=str, help="result conf path")
            parser.add_argument("--dsl", required=True, type=str, help="dsl")
            parser.add_argument("--runtime_conf", required=True, type=str, help="runtime_conf")
            parser.add_argument("--train_runtime_conf", required=True, type=str, help="train_runtime_conf")
            parser.add_argument("--pipeline_dsl", required=True, type=str, help="pipeline_dsl")
            parser.add_argument("--run_ip", help="run ip", type=str)
            parser.add_argument("--job_server", help="job server", type=str)
            args = parser.parse_args()
            job_id = args.job_id
            role = args.role
            party_id = args.party_id
            schedule_logger(job_id).info("enter task initializer process")
            schedule_logger(job_id).info(args)
            schedule_logger(job_id).info("python env: {}, python path: {}".format(os.getenv("VIRTUAL_ENV"), os.getenv("PYTHONPATH")))
            # init function args
            if args.job_server:
                RuntimeConfig.init_config(JOB_SERVER_HOST=args.job_server.split(":")[0],
                                          HTTP_PORT=args.job_server.split(":")[1])
                RuntimeConfig.set_process_role(ProcessRole.EXECUTOR)
            start_time = current_timestamp()
            ComponentRegistry.load()
            job_dsl = file_utils.load_json_conf(args.dsl)
            job_runtime_conf = file_utils.load_json_conf(args.runtime_conf)
            train_runtime_conf = file_utils.load_json_conf(args.train_runtime_conf)
            pipeline_dsl = file_utils.load_json_conf(args.pipeline_dsl)
            dsl_parser = schedule_utils.get_job_dsl_parser(dsl=job_dsl,
                                                           runtime_conf=job_runtime_conf,
                                                           train_runtime_conf=train_runtime_conf,
                                                           pipeline_dsl=pipeline_dsl)

            initialized_config = file_utils.load_json_conf(args.config)
            provider = ComponentProvider(**initialized_config["provider"])
            common_task_info = initialized_config["common_task_info"]
            need_run_components = {}
            for component_name in initialized_config["components"]:
                result[component_name] = {}
                task_info = {}
                task_info.update(common_task_info)

                parameters = ProviderManager.get_component_parameters(dsl_parser=dsl_parser,
                                                                      component_name=component_name,
                                                                      role=role,
                                                                      party_id=party_id,
                                                                      provider=provider)
                if parameters:
                    task_info = {}
                    task_info.update(common_task_info)
                    task_info["component_name"] = component_name
                    task_info["component_module"] = parameters["module"]
                    task_info["provider_info"] = provider.to_dict()
                    task_info["component_parameters"] = parameters
                    TaskController.create_task(role=role, party_id=party_id,
                                               run_on_this_party=common_task_info["run_on_this_party"],
                                               task_info=task_info)
                    result[component_name]["need_run"] = True
                else:
                    # The party does not need to run, pass
                    result[component_name]["need_run"] = False
            end_time = current_timestamp()
            elapsed = end_time - start_time
            schedule_logger().info(
                "job {} component {} is initialized on {} {} use {} ms".format(job_id, need_run_components.values(), role,
                                                                               party_id, elapsed))
            file_utils.dump_json_conf(result, args.result)
        except Exception as e:
            traceback.print_exc()
            schedule_logger().exception(e)
            sys.exit(1)


if __name__ == "__main__":
    TaskInitializer.run()
