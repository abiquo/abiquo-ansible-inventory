# External inventory script for Abiquo

Shamelessly copied from an existing inventory script.

This script generates an inventory that Ansible can understand by making API requests to Abiquo API.
It does require some python libraries, ensure to have them installed when using this script. You can install
all the dependencies by running:

```
pip install -r requirements.txt
```

This script has been tested in Abiquo 4.2 but it may also work with different Abiquo versions.

Before using this script you may want to modify abiquo.ini config file.

## Configuration

The script can be configured with an `abiquo_inventory.ini` file or using environment variables. Check the supplied `abiquo_inventory.ini` file for more information.

## Usage

See the help:

```
$ ./abiquo_inventory.py --help
usage: abiquo_inventory.py [-h] [--list] [--host HOST] [--refresh-cache]

Produce an Ansible Inventory file based on Abiquo VMs

optional arguments:
  -h, --help       show this help message and exit
  --list           List VMs (default: True)
  --host HOST      Get all the variables about a specific VM
  --refresh-cache  Force refresh of cache by making API requests (default:
                   False - use cache files)
```

## Output

This script generates an Ansible hosts file with these host groups:

- `ABQ_xxx`: Defines a hosts itself by Abiquo VM name.
- `dstier_TIER_NAME`: Includes all the VMs which have one or more disks in the datastore tier described by `TIER_NAME`.
- `firewall_FW_NAME`: Includes all the VMs which have assigned the firewall with name `FW_NAME`.
- `hwprof_HWPROFILE`: Includes all the VMs using the hardware profile with name `HWPROFILE`.
- `loadbalancer_LB_NAME`: Includes all the VMs which are included as nodes in the loadbalancer with name `LB_NAME`.
- `network_NET_NAME`: Includes all the VMs which are connected to the network with name `NET_NAME`.
- `template_TEMPLATENAME`: Includes all the VMs created from the template with name `TEMPLATENAME`.
- `vdc_VDC_NAME`: Includes all the VMs inside the virtual datacenter with name `VDC_NAME`.
- `vapp_VAPP_NAME`: Includes all the VMs inside the virtual appliance with name `VAPP_NAME`.
- `vdc_VDC_NAME_vapp_VAPP_NAME`: Includes all the VMs inside the virtual appliance with name `VAPP_NAME` inside the virtual datacenter with name `VDC_NAME`.
- `var_VARNAME_VARVALUE`: Includes all the VMs for each variable/value pair. It will contain all the hosts
for which VM variable VARNAME has value VARVALUE.

# License and Authors

* Author:: Daniel Beneyto (daniel.beneyto@abiquo.com)
* Author:: Marc Cirauqui (marc.cirauqui@abiquo.com)

Copyright:: 2014, Abiquo

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
