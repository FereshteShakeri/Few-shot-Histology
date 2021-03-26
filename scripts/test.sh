method=$1
shot=$2

base_config_path="config/base.yaml"
method_config_path="config/${method}.yaml"

python3 -m src.test --base_config ${base_config_path} \
                    --method_config ${method_config_path} \
                    --opts num_support ${shot} \
                           visu True