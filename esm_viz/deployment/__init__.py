#!/bin/python
"""
This package reads a "namelist", since Chris really, really wanted one. It then
deploys a series of analysis scripts to a remote host, and combines several
jupyter notebooks together to achieve a monitoring system for any
particular experiment.

This portion of the package contains the following pieces:
    + reading the configuration yaml file to determine what is being monitored
    + a class to contain deployment infrastructure; copying analysis scripts to
      the other computer and running them

Note: ESM-style directory structures are assumed. Otherwise, I'm just at a
loss...

Dr. Paul Gierz
March 2019
"""
import logging
import os
import sys

import paramiko


__author__ = "Danek, Gierz, Stepanek"
__version__ = "0.1.0"  # FIXME: Bump this to 1.0.0 once it works


def rexists(sftp, path):
    """os.path.exists for paramiko's SCP object"""
    try:
        sftp.stat(path)
        return True
    except FileNotFoundError:
        return False


class Simulation_Monitor(object):
    """
    ``Simulation_Monitor`` can deploy and run simulation monitoring scripts.

    The golden idea here is to automatically deploy certain scripts to a
    production machine, and run them with some (ideally useful) arguments. In
    principle, we need two methods for this:

    1. something that copies the script
    1. something that runs the script.

    Methods
    -------
    + copy_analysis_script_for_component:
        Copies a specified analysis script to a folder EXPBASE/analysis/<component>
    + run_analysis_script_for_component:
        Runs an analysis script with a passed set of arguments.
    """
    def __init__(self, user, host, basedir):
        """
        Initializes a new monitoring object.

        Attributes
        ----------
        basedir : str
            The directory where the experiment is running. Should point to the
            top of the experiment
        host : str
            The compute host
        user : str
            The username
        ssh : paramiko.SSHClient
            A ssh client which you can use to connect to the host (maybe this
            should be automatically connected)
        """
        self.basedir = basedir
        self.host = host
        self.user = user
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if not self._can_login_to_host_without_password():
            with open(os.environ["HOME"]+"/simulation_monitoring_errors", "a") as error_file:
                error_file.write("Hey, you should setup ssh keys for %s. Try using esm-viz/deployment/generate_automatic_ssh_key.sh" % host)
                error_file.write("Cowardly refusing to do anything until you get your keys figured out. Goodbye.")
                logging.error("Hey, you can't log on to this computer: %s. Set up your keys!!! See also the error message in your home folder!", self.host)
                sys.exit()

    def _can_login_to_host_without_password(self):
        """
        Tries to figure out if you can log into the host without a password.

        Returns
        -------
        bool
            ``True`` if you can log in to the instance's ``host`` without a
            password. Otherwise, ``False``.
        """
        try:
            self.ssh.connect(self.host, username=self.user)
            self.ssh.close()
            return True
        # FIXME: Maybe we really just need a general except here...
        except paramiko.ssh_exception.AuthenticationException:
            return False

    def copy_analysis_script_for_component(self, component, analysis_script, coupling_setup=None):
        """
        Copies a specific analysis script to the correct folder.

        Parameters:
        -----------
        component : str
            The component that will be automatically monitored
        analysis_script : str
            The script that will automatically analyze this component
        """
        self.ssh.connect(self.host, username=self.user)
        with self.ssh.open_sftp() as sftp:
            if coupling:
                remote_analysis_script_directory = self.basedir+"/"+coupling_setup+"/"+component
            else:
                remote_analysis_script_directory = self.basedir + "/analysis/" + component
            if not rexists(sftp, remote_analysis_script_directory):
                sftp.mkdir(remote_analysis_script_directory)
            if not rexists(sftp, remote_analysis_script_directory+"/"+os.path.basename(analysis_script)):
                logging.info("Copying %s to %s", os.path.basename(analysis_script), remote_analysis_script_directory)
                sftp.put(analysis_script, remote_analysis_script_directory+"/"+os.path.basename(analysis_script))
            logging.info(sftp.stat(remote_analysis_script_directory+"/"+os.path.basename(analysis_script)))
            sftp.chmod(remote_analysis_script_directory+"/"+os.path.basename(analysis_script), 0o755)
            logging.info(sftp.stat(remote_analysis_script_directory+"/"+os.path.basename(analysis_script)))
        self.ssh.close()

    def run_analysis_script_for_component(self, component, analysis_script, args=[]):
        """
        Runs a script with arguments for a specific component

        Parameters:
        -----------
        component : str
            Which component to run scripts for
        analysis_script : str
            Which script to run
        args : list
            A list of strings for the arguments. If the arguments need flags,
            they should get "-<FLAG NAME>" as one of the strings
        """
        self.ssh.connect(self.host, username=self.user)
        logging.info("Executing...")
        self.ssh.invoke_shell()
        args = [arg.replace("$", "\$").replace("{", "\{").replace("}", "\}") for arg in args]
        stdin, stdout, stderr = self.ssh.exec_command("bash -l -c 'cd "+self.basedir+"/analysis/"+component+"; "+" ".join(["./"+analysis_script] + args + ["'"]),
                get_pty=True)
        for stream, tag in zip([stdin, stdout, stderr], ["stdin", "stdout", "stderr"]):
            try:
                logging.info(tag)
                for line in stream.readlines():
                    logging.info(line)
            except OSError:
                logging.info("Couldn't open %s", tag)
        self.ssh.close()
