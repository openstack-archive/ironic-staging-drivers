.. _intel_nm:

#########################
Intel NodeManager drivers
#########################

Overview
========

This driver implements support of Intel NodeManager platform via ironic
vendor interface methods. Those methods are implemented as sending raw bytes
over IPMI.
Hardware with Intel NodeManager 1.5 or above is required, feature must be
enabled via Flash Image Tool. The driver detects internal addresses of
NodeManager device automatically.
The main term for NodeManager is ``policy``, which can be power, thermal or
boot time. Each policy identified by ``policy_id`` (integer number from 0 to
255). Maximum numbers of policies which can be set at the same time limited by
platform. For more detailed information see full specification [1]_.

The ``staging-nm`` hardware types extends the ``ipmi`` hardware type with
support for the ``staging-nm`` vendor interface.

Supported vendor passthru methods
=================================

In all examples below request/response are JSON bodies in the HTTP request
or response.

get_nm_version
--------------

HTTP method
    GET

Description
    Get Intel Node Manager version.

Example of response::

  {"firmware": "1.2", "ipmi": "3.0", "nm": "3.0", "patch": "7"}

get_nm_capabilities
-------------------

HTTP method
    GET

Description
    Get Intel Node Manager capabilities.

Example of request::

  {"domain_id": "platform", "policy_trigger": "none",
   "power_domain": "primary"}

Example of response::

  {"domain_id": "platform", "max_correction_time": 100000,
   "max_limit_value": 4096, "max_policies": 16,
   "max_reporting_period": 32768, "min_correction_time": 10,
   "min_limit_value": 100, "min_reporting_period": 100,
   "power_domain": "primary"}

control_nm_policy
-----------------

HTTP method
    PUT

Description
    Enable or disable Intel Node Manager policy control.

Example of request::

  {"scope": "policy", "enable": false, "policy_id": 10}

set_nm_policy
-------------

HTTP method
    PUT

Description
    Set Intel Node Manager policy. This method creates new policy if provided
    ``policy_id`` is not present or changes current policy.

Example of request::

  {"domain_id": "platform", "enable": true, "policy_id": 10,
   "policy_trigger": "none", "action": "alert", "power_domain": "primary",
   "target_limit": 200, "reporting_period": 20000}

get_nm_policy
-------------

HTTP method
    GET

Description
    Get Intel Node Manager policy.

Example of request::

  {"domain_id": "platform", "policy_id": 11}

Example of response::

  {"action": "alert", "correction_time": 10000, "cpu_power_correction": "auto",
   "created_by_nm": true, "domain_id": "platform", "enabled": true,
   "global_enabled": true, "per_domain_enabled": true,
   "policy_trigger": "none", "power_domain": "primary", "power_policy": false,
   "reporting_period": 20000, "storage": "persistent", "target_limit": 250,
   "trigger_limit": 300}

remove_nm_policy
----------------

HTTP method
    DELETE

Description
    Remove Intel Node Manager policy.

Example of request::

  {"domain_id": "platform", "policy_id": 11}

set_nm_policy_suspend
---------------------

HTTP method
    PUT

Description
    Set Intel Node Manager policy suspend periods.

Example of request::

 {"domain_id": "platform", "policy_id": 10,
  "periods": [{"start": 10, "stop": 60, "days": ["monday", "tuesday"]}]}

For information about time periods calculation please read NodeManager
specification.

get_nm_policy_suspend
---------------------

HTTP method
    GET

Description
    Get Intel Node Manager policy suspend periods.

Example of request::

  {"domain_id": "platform", "policy_id": 13}

Example of response::

  {"domain_id": "platform", "policy_id": 13,
   "periods": [{"start": 20, "stop": 100, "days": ["monday", "tuesday"]},
               {"start": 30, "stop": 150, "days": ["friday", "sunday"]}]}

remove_nm_policy_suspend
------------------------

HTTP method
    DELETE

Description
    Remove Intel Node Manager policy suspend periods.

Example of request::

  {"domain_id": "platform", "policy_id": 13}

get_nm_statistics
-----------------

HTTP method
    GET

Description
    Get Intel Node Manager statistics.

Example of request::

  {"scope": "global", "domain_id": "platform", "parameter_name": "power"}

Example of response::

  {"activation_state": true, "administrative_enabled": true,
   "average_value": 200, "current_value": 202, "domain_id": "platform",
   "maximum_value": 240, "measurement_state": true, "minimum_value": 150,
   "operational_state": true, "reporting_period": 2125,
   "timestamp": "2016-02-03T20:13:52"}

reset_nm_statistics
-------------------

HTTP method
    DELETE

Description
    Reset Intel Node Manager statistics.

Example of request::

  {"scope": "global", "domain_id": "platform"}


References
==========
.. [1] http://www.intel.com/content/www/us/en/power-management/intelligent-power-node-manager-3-0-specification.html
