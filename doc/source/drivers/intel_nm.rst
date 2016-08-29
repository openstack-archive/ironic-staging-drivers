.. _intel_nm:

#########################
Intel NodeManager drivers
#########################

Overview
========

This driver implements vendor interface presenting functionality available
in Intel NodeManager platform.
It mainly concerns getting/setting thermal policies and statistics.

Those methods are implemented as sending raw bytes over IPMI.

Available drivers
=================

Driver provided by ironic-staging-drivers are

agent_ipmitool_nm
    Standard Ironic's ``agent_ipmitool`` driver with Intel NodeManager
    as vendor extension

fake_nm
    Used for testing of this vendor passthru extension.


Supported vendor passthru methods
=================================

get_nm_version
--------------

HTTP method
    GET

Description
    Get Intel Node Manager version

control_nm_policy
-----------------

HTTP method
    PUT

Description
    Enable or disable Intel Node Manager policy control

set_nm_policy
-------------

HTTP method
    PUT

Description
    Get Intel Node Manager policy

get_nm_policy
-------------

HTTP method
    GET

Description
    Get Intel Node Manager policy

remove_nm_policy
----------------

HTTP method
    DELETE

Description
    Remove Intel Node Manager policy

set_nm_policy_suspend
---------------------

HTTP method
    PUT

Description
    Set Intel Node Manager policy suspend periods.

get_nm_policy_suspend
---------------------

HTTP method
    GET

Description
    Get Intel Node Manager policy suspend periods.

remove_nm_policy_suspend
------------------------

HTTP method
    DELETE

Description
    Remove Intel Node Manager policy suspend periods.

get_nm_capabilities
-------------------

HTTP method
    GET

Description
    Get Intel Node Manager capabilities.

get_nm_statistics
-----------------

HTTP method
    GET

Description
    Get Intel Node Manager statistics.

reset_nm_statistics
-------------------

HTTP method
    DELETE

Description
    Reset Intel Node Manager statistics.
