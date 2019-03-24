======================
Ironic Staging Drivers
======================

The Ironic Staging Drivers is used to hold out-of-tree Ironic drivers
which doesn't have means to provide a 3rd Party CI at this point in
time which is required by Ironic.

The intention of this project is to provide a common place for useful
drivers resolving the "hundreds of different download sites" problem.


What the Ironic Staging Drivers is not
---------------------------------------

* The Ironic Staging Drivers is **not** a project under Ironic's
  governance, meaning that the Ironic core group is **not responsible**
  for the code in this project (even though, some individuals that work in
  this project also hold core status in the Ironic project).

* This project is **not** a place to dump code and run away hoping that
  someone else will take care of it for you. Drivers included
  in this project should be maintained and have their bugs fixed
  quickly. Therefore, driver owners are going to be asked to "babysit"
  their driver.


How to contribute
-----------------

We want to make sure that the Ironic Staging Drivers project is a
welcoming and friendly place to contribute code. Therefore, we want to
avoid bureaucratic processes as much as possible. If you want to propose
a driver to be included in the repository: Just submit the code!

How do I submit the code?
^^^^^^^^^^^^^^^^^^^^^^^^^

#. Before we can accept your patches, you'll
   have to `agree to a contributor license agreement
   <https://docs.openstack.org/infra/manual/developers.html#account-setup>`_.

#. Learn about `how to use our Gerrit review system
   <https://docs.openstack.org/infra/manual/developers.html#development-workflow>`_.

#. Get the code::

     git clone https://git.openstack.org/openstack/ironic-staging-drivers

#. Make your changes and write a nice commit message explaining the
   change in details.

#. Submit the code!


Useful links
------------

* Free software: Apache license
* Documentation: http://ironic-staging-drivers.readthedocs.io/en/latest/
* Source: http://git.openstack.org/cgit/openstack/ironic-staging-drivers
* Bugs: https://storyboard.openstack.org/#!/project/950
