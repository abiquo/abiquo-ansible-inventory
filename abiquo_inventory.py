#!/usr/bin/env python
# -*- coding: utf-8 -*-

# (c) 2014, Daniel Beneyto <daniel.beneyto@abiquo.com>
#           Marc Cirauqui <marc.cirauqui@abiquo.com>
#
# This file is part of Ansible,
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

import os
import copy
import sys
import traceback
import time
import requests
import argparse
import urllib3
import httplib as http_client
from abiquo.client import Abiquo, check_response
from requests_oauthlib import OAuth1
from os.path import expanduser

try:
    import ConfigParser # py2
except ImportError:
    import configparser # py3

try:
    from http.client import HTTPConnection # py3
except ImportError:
    from httplib import HTTPConnection # py2

try:
    import json
except ImportError:
    import simplejson as json

import pdb

class AbiquoInventory(object):
    def _empty_inventory(self):
        return {"_meta": {"hostvars": {}}}

    def __init__(self):
        ''' Main execution path '''
        self.inventory = self._empty_inventory()

        '''Initialise'''
        self.parse_cli_args()
        self.get_config()
        self.init_client()

        if self.args.refresh_cache:
            inv = self.generate_inv_from_api()
        elif not self.cache_available():
            inv = self.generate_inv_from_api()
        else:
            inv = self.get_cache()

        if self.cache_enabled():
            self.save_cache(inv)

        if self.args.host:
            sys.stdout.write(json.dumps(inv['_meta']['hostvars'][self.args.host], sort_keys=True, indent=2))
        else:
            sys.stdout.write(json.dumps(inv, sort_keys=True, indent=2))
    
    def fail_with_error(self, e):
        sys.stderr.write(str(e))
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)

    def parse_cli_args(self):
        ''' Command line argument processing '''
        parser = argparse.ArgumentParser(description='Produce an Ansible Inventory file based on Abiquo VMs')
        parser.add_argument('--list', action='store_true', default=True,
                            help='List VMs (default: True)')
        parser.add_argument('--host', action='store',
                            help='Get all the variables about a specific VM')
        parser.add_argument('--refresh-cache', action='store_true', default=False,
                            help='Force refresh of cache by making API requests (default: False - use cache files)')
        self.args = parser.parse_args()

    def get_config(self):
        ''' Read config file '''
        configfilename = os.path.splitext(os.path.abspath(sys.argv[0]))[0] + '.ini'

        try:
            os.stat(configfilename)

            config = ConfigParser.SafeConfigParser()
            config.read(configfilename)
            self.config = config
        except:
            self.config = ConfigParser.SafeConfigParser()

    def init_client(self):
        api_url = self.config_get('api', 'uri')
        verify = self.config.getboolean('api', 'ssl_verify') if self.config.has_option('api', 'ssl_verify') else None
        api_user = self.config_get('auth', 'apiuser')
        api_pass = self.config_get('auth', 'apipass')
        app_key = self.config_get('auth', 'api_key')
        app_secret = self.config_get('auth', 'api_secret')
        token = self.config_get('auth', 'token')
        token_secret = self.config_get('auth', 'token_secret')

        # API URL
        if not api_url:
            if os.environ.get('ABIQUO_API_URL') is not None and os.environ.get('ABIQUO_API_URL') != "":
                api_url = os.environ.get('ABIQUO_API_URL')
            else:
                raise ValueError('Abiquo API URL is missing!!')

        if os.environ.get('ABIQUO_API_INSECURE') is not None:
            verify = False

        # Basic auth
        if not api_user:
            if os.environ.get('ABIQUO_API_USERNAME') is not None and os.environ.get('ABIQUO_API_USERNAME') != "":
                api_user = os.environ.get('ABIQUO_API_USERNAME')
        if not api_pass:
            if os.environ.get('ABIQUO_API_PASSWORD') is not None and os.environ.get('ABIQUO_API_PASSWORD') != "":
                api_pass = os.environ.get('ABIQUO_API_PASSWORD')

        # OAuth1
        if not app_key:
            if os.environ.get('ABIQUO_API_APP_KEY') is not None and os.environ.get('ABIQUO_API_APP_KEY') != "":
                app_key = os.environ.get('ABIQUO_API_APP_KEY')
        if not app_secret:
            if os.environ.get('ABIQUO_API_APP_SECRET') is not None and os.environ.get('ABIQUO_API_APP_SECRET') != "":
                app_secret = os.environ.get('ABIQUO_API_APP_SECRET')
        if not token:
            if os.environ.get('ABIQUO_API_TOKEN') is not None and os.environ.get('ABIQUO_API_TOKEN') != "":
                token = os.environ.get('ABIQUO_API_TOKEN')
        if not token_secret:
            if os.environ.get('ABIQUO_API_TOKEN_SECRET') is not None and os.environ.get('ABIQUO_API_TOKEN_SECRET') != "":
                token_secret = os.environ.get('ABIQUO_API_TOKEN_SECRET')

        if api_user is not None:
            creds = (api_user, api_pass)
        elif app_key is not None:
            creds = OAuth1(app_key,
                        client_secret=app_secret,
                        resource_owner_key=token,
                        resource_owner_secret=token_secret)
        else:
            raise ValueError('Either basic auth or OAuth creds are required.')

        self.api = Abiquo(api_url, auth=creds, verify=verify)
        if not verify:
            urllib3.disable_warnings()

        if os.environ.get('ABQ_DEBUG'):
            HTTPConnection.debuglevel = 1

    def config_get(self, section, option):
        return self.config.get(section, option) if self.config.has_option(section, option) else None

    def cache_enabled(self):
        use_cache = True
        if self.config.has_option('cache', 'use_cache'):
            use_cache = self.config.getboolean('cache', 'use_cache')

        if os.environ.get("ABIQUO_INV_CACHE_DISABLE"):
            use_cache = False

        return use_cache

    def cache_file(self):
        env_cache_dir = os.getenv("ABIQUO_INV_CACHE_DIR")
        if env_cache_dir is not None:
            return os.path.expanduser(os.path.join(env_cache_dir, 'abiquo-inventory'))
        elif self.config.has_option('cache', 'cache_dir'):
            return os.path.expanduser(os.path.join(self.config.get('cache', 'cache_dir'), 'abiquo-inventory'))
        else:
            return os.path.expanduser(os.path.join('~', '.ansible', 'tmp', 'abiquo-inventory'))
            
    def cache_ttl(self):
        env_cache_ttl = os.getenv("ABIQUO_INV_CACHE_TTL")
        if env_cache_ttl is not None:
            return int(env_cache_ttl)
        elif self.config.has_option('cache', 'cache_max_age'):
            return self.config.getint('cache', 'cache_max_age')
        else:
            return 600

    def cache_available(self):
        ''' checks if we have a 'fresh' cache available for item requested '''
        try:
            existing = os.stat(self.cache_file())
        except:
            return False

        if ((int(time.time()) - int(existing.st_mtime)) <= self.cache_ttl()):
            return True

        return False

    def get_cache(self):
        ''' returns cached item  '''
        inv = {}
        try:
            cache = open(self.cache_file(), 'r')
            inv = json.loads(cache.read())
            cache.close()
        except IOError:
            pass # not really sure what to do here

        return inv

    def save_cache(self, data):
        ''' saves item to cache '''
        try:
            cache = open(self.cache_file(), 'w+')
            cache.write(json.dumps(data))
            cache.close()
        except IOError:
            pass # not really sure what to do here

    def get_vms(self):
        code, vms = self.api.cloud.virtualmachines.get(headers={'accept':'application/vnd.abiquo.virtualmachines+json'})
        try:
            check_response(200, code, vms)
        except Exception as e:
            self.fail_with_error(e)
        return vms

    def update_vm_metadata(self, vm):
        code, metadata = vm.follow('metadata').get()
        try:
            check_response(200, code, metadata)
        except Exception as e:
            self.fail_with_error(e)
        vm.json['metadata'] = metadata.json

    def update_vm_template(self, vm):
        template = self.get_vm_template(vm)
        json = template.json
        del json['links']
        vm.json['template'] = json

    def update_vm_disks_and_nics(self, vm):
        vm_nics = []
        vm_disks = []
        vm_vols = []
        nics = self.get_vm_nics(vm)
        disks = self.get_vm_disks(vm)
        vols = self.get_vm_volumes(vm)

        for nic in nics:
            vm_nics.append(nic.json)

        for disk in disks:
            vm_disks.append(disk.json)

        for vol in vols:
            vm_disks.append(vol.json)

        vm.json['nics'] = vm_nics
        vm.json['disks'] = vm_disks

    def get_vm_template(self, vm):
        code, template = vm.follow('virtualmachinetemplate').get()
        try:
            check_response(200, code, template)
        except Exception as e:
            self.fail_with_error(e)
        return template

    def get_vm_nics(self, vm):
        code, nics = vm.follow('nics').get()
        try:
            check_response(200, code, nics)
        except Exception as e:
            self.fail_with_error(e)
        return nics

    def get_vm_disks(self, vm):
        code, disks = vm.follow('harddisks').get()
        try:
            check_response(200, code, disks)
        except Exception as e:
            self.fail_with_error(e)

        return disks

    def get_vm_volumes(self, vm):
        code, vols = vm.follow('volumes').get()
        try:
            check_response(200, code, vols)
        except Exception as e:
            self.fail_with_error(e)

        return vols
    
    def get_vm_network_names(self, vm):
        net_names = []
        code, nics = vm.follow('nics').get()
        try:
            check_response(200, code, nics)
            for nic in nics:
                private_nic_link = nic._extract_link('privatenetwork')
                ext_nic_link = nic._extract_link('externalnetwork')
                pub_nic_link = nic._extract_link('publicnetwork')

                if private_nic_link is not None:
                    net_names.append(private_nic_link['title'])
                elif ext_nic_link is not None:
                    net_names.append(ext_nic_link['title'])
                elif pub_nic_link is not None:
                    net_names.append(pub_nic_link['title'])
                else:
                    continue
            return net_names
        except Exception as e:
            self.fail_with_error(e)
    
    def get_vm_ds_tiers_names(self, vm):
        tier_names = []
        ds_tier_links = filter(lambda x: x['rel'].startswith('datastoretier'), vm.links)

        for tier_link in ds_tier_links:
            if tier_link['title'] not in tier_names:
                tier_names.append(tier_link['title'])

        return tier_names
    
    def get_vm_firewall_names(self, vm):
        fw_names = []
        fw_links = filter(lambda x: x['rel'] == 'firewall', vm.links)

        for fw_link in fw_links:
            if fw_link['title'] not in fw_names:
                fw_names.append(fw_link['title'])

        return fw_names

    def get_vm_loadbalancer_names(self, vm):
        lb_names = []
        lb_links = filter(lambda x: x['rel'] == 'loadbalancer', vm.links)

        for lb_link in lb_links:
            if lb_link['title'] not in lb_names:
                lb_names.append(lb_link['title'])

        return lb_names

    def nic_json_to_dict(self, nics_json):
        nics = copy.copy(nics_json)
        nic_dict = {}

        for nic in nics:
            nic_rel = "nic%d" % nic['sequence']
            for key in nic:
                if key != 'links':
                    nic_dict["%s_%s" % (nic_rel, key)] = nic[key]

            netlink = filter(lambda x: "network" in x['rel'], nic['links'])
            if len(netlink) > 0:
                netlink = netlink[0]
                nic_dict["%s_net_type" % nic_rel] = netlink['rel']

        return nic_dict

    def disk_json_to_dict(self, disks_json):
        disks = copy.copy(disks_json)
        disk_dict = {}

        for disk in disks:
            disk_rel = "disk%d" % disk['sequence']
            for key in disk:
                if key != 'links':
                    disk_dict["%s_%s" % (disk_rel, key)] = disk[key]

            tierlink = filter(lambda x: "tier" in x['rel'], disk['links'])
            if len(tierlink) > 0:
                tierlink = tierlink[0]
                disk_dict["%s_tier" % disk_rel] = tierlink['title']

        return disk_dict
    
    def sanitize_name(self, name):
        return name.replace('[','').replace(']','').replace(' ','_').replace('/','_')

    def vars_from_json(self, vm_json):
        vm = copy.copy(vm_json)
        nics_dict = self.nic_json_to_dict(vm['nics'])
        disks_dict = self.disk_json_to_dict(vm['disks'])

        host_vars = dict(nics_dict.items() + disks_dict.items())

        link_rels = [
            "category", "virtualmachinetemplate", "hypervisortype", "ip", "location", "hardwareprofile",
            "state", "network_configuration", "virtualappliance", "virtualdatacenter", "user", "enterprise"
        ]
        vm_links = copy.copy(vm['links'])
        link_dict = {}
        for rel in link_rels:
            links = filter(lambda y: y['rel'] == rel, vm_links)
            if len(links) > 0:
                link = links[0]
                k = link['rel']
                v = link['title']
                link_dict[k] = v

        attrs_dict = copy.copy(vm)
        del attrs_dict['links']
        del attrs_dict['nics']
        del attrs_dict['disks']

        d = dict(host_vars.items() + link_dict.items() + attrs_dict.items())
        for i in d:
            if not i.startswith('abq'):
                d['abq_%s' % i] = d.pop(i)

        return d

    def generate_inv_from_api(self):
        inventory = self.inventory
        try:
            vms = self.get_vms()
            config = self.config
            for vm in vms:
                self.update_vm_disks_and_nics(vm)
                self.update_vm_template(vm)
                get_md = os.environ.get("ABIQUO_INV_GET_METADATA")
                if not get_md:
                    get_md = config.getboolean('defaults', 'get_metadata') if config.has_option('defaults', 'get_metadata') else False
                if get_md:
                    self.update_vm_metadata(vm)

                host_vars = self.vars_from_json(vm.json)

                hw_profile = ''
                for link in vm.links:
                    if link['rel'] == 'virtualappliance':
                        vm_vapp = link['title'].replace('[','').replace(']','').replace(' ','_')
                    elif link['rel'] == 'virtualdatacenter':
                        vm_vdc = link['title'].replace('[','').replace(']','').replace(' ','_')
                    elif link['rel'] == 'virtualmachinetemplate':
                        vm_template = link['title'].replace('[','').replace(']','').replace(' ','_')
                    elif link['rel'] == 'hardwareprofile':
                        hw_profile = link['title'].replace('[','').replace(']','').replace(' ','_')

                # From abiquo.ini: Only adding to inventory VMs with public IP
                public_ip_only = os.environ.get("ABIQUO_INV_PUBLIC_IP_ONLY")
                if not public_ip_only:
                    public_ip_only = config.getboolean('defaults', 'public_ip_only') if config.has_option('defaults', 'public_ip_only') else False

                if public_ip_only:
                    for link in vm.links:
                        if (link['type']=='application/vnd.abiquo.publicip+json' and link['rel']=='ip'):
                            vm_nic = link['title']
                            break
                        else:
                            vm_nic = None
                # Otherwise, assigning defined network interface IP address
                else:
                    default_net_iface = os.environ.get("ABIQUO_INV_DEFAULT_IFACE")
                    if not default_net_iface:
                        default_net_iface = config.get('defaults', 'default_net_interface') if config.has_option('defaults', 'default_net_interface') else "nic0"

                    for link in vm.links:
                        if link['rel'] == default_net_iface:
                            vm_nic = link['title']
                            break
                        else:
                            vm_nic = None

                if vm_nic is None:
                    continue

                vm_state = True
                # From abiquo.ini: Only adding to inventory VMs deployed
                deployed_only = os.environ.get("ABIQUO_INV_DEPLOYED_ONLY")
                if not deployed_only:
                    deployed_only = config.getboolean('defaults', 'deployed_only') if config.has_option('defaults', 'deployed_only') else True

                if deployed_only and vm.state == 'NOT_ALLOCATED':
                    vm_state = False

                if not vm_state:
                    continue

                # Retrieve network names the VM is connected to
                network_names = self.get_vm_network_names(vm)

                # Retrieve DS tiers the VM is using
                ds_tier_names = self.get_vm_ds_tiers_names(vm)

                # Retrieve Firewall names
                firewall_names = self.get_vm_firewall_names(vm)

                # Retrieve LoadBalancer names
                loadbalancer_names = self.get_vm_loadbalancer_names(vm)

                ## Set host vars
                inventory['_meta']['hostvars'][vm_nic] = host_vars

                ## Start with groupings

                # VM name
                if vm.name not in inventory:
                    inventory[vm.name] = []
                inventory[vm.name].append(vm_nic)

                # VM template
                vm_tmpl = "template_%s" % vm_template
                if vm_tmpl not in inventory:
                    inventory[vm_tmpl] = []
                inventory[vm_tmpl].append(vm_nic)

                # vApp
                vapp = "vapp_%s" % vm_vapp
                if vapp not in inventory:
                    inventory[vapp] = []
                inventory[vapp].append(vm_nic)

                # VDC
                vdc = "vdc_%s" % vm_vdc
                if vdc not in inventory:
                    inventory[vdc] = []
                inventory[vdc].append(vm_nic)

                # VDC_vApp
                vdcvapp = 'vdc_%s_vapp_%s' % (vm_vdc, vm_vapp)
                if vdcvapp not in inventory:
                    inventory[vdcvapp] = []
                inventory[vdcvapp].append(vm_nic)

                # HW profiles
                if hw_profile != '':
                    hwprof = 'hwprof_%s' % hw_profile
                    if hwprof not in inventory:
                        inventory[hwprof] = []
                    inventory[hwprof].append(vm_nic)

                # VM variables
                if 'variables' in vm.json:
                    for var in vm.json['variables']:
                        var_sane = self.sanitize_name(var)
                        val_sane = self.sanitize_name(vm.json['variables'][var])
                        vargroup = "var_%s_%s" % (var_sane, val_sane)
                        if vargroup not in inventory:
                            inventory[vargroup] = []
                        inventory[vargroup].append(vm_nic)
                
                # Networks names
                for name in network_names:
                    name_sane = self.sanitize_name(name)
                    net_key = "network_%s" % name_sane
                    if net_key not in inventory:
                        inventory[net_key] = []
                    inventory[net_key].append(vm_nic)

                # DS Tier names
                for name in ds_tier_names:
                    name_sane = self.sanitize_name(name)
                    tier_key = "dstier_%s" % name_sane
                    if tier_key not in inventory:
                        inventory[tier_key] = []
                    inventory[tier_key].append(vm_nic)
                
                # Firewall names
                for name in firewall_names:
                    name_sane = self.sanitize_name(name)
                    fw_key = "firewall_%s" % name_sane
                    if fw_key not in inventory:
                        inventory[fw_key] = []
                    inventory[fw_key].append(vm_nic)

                # Loadbalancer names
                for name in loadbalancer_names:
                    name_sane = self.sanitize_name(name)
                    lb_key = "loadbalancer_%s" % name_sane
                    if lb_key not in inventory:
                        inventory[lb_key] = []
                    inventory[lb_key].append(vm_nic)

            return inventory
        except Exception:
            # Return empty hosts output
            sys.stderr.write(traceback.format_exc())
            return self._empty_inventory()

if __name__ == '__main__':
    AbiquoInventory()
