import os

from avocado.utils import aurl, download
from virttest import data_dir, error_context, utils_test

CLIENT_TEST = "kernelinstall"


@error_context.context_aware
def run(test, params, env):
    """
    KVM kernel install test:
    1) Log into a guest
    2) Save current default kernel information
    3) Fetch necessary files for guest kernel installation
    4) Generate control file for kernel install test
    5) Launch kernel installation (kernel install) test in guest
    6) Reboot guest after kernel is installed (optional)
    7) Do sub tests in guest with new kernel (optional)
    8) Restore grub and reboot guest (optional)

    :param test: kvm test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment.
    """
    sub_test_path = os.path.join(test.bindir, "../%s" % CLIENT_TEST)
    _tmp_file_list = []
    _tmp_params_dict = {}

    def _copy_file_to_test_dir(file_path):
        if aurl.is_url(file_path):
            return file_path
        file_abs_path = os.path.join(test.bindir, file_path)
        dest = os.path.join(sub_test_path, os.path.basename(file_abs_path))
        return os.path.basename(download.get_file(file_path, dest))

    def _save_bootloader_config(session):
        """
        Save bootloader's config, in most case, it's grub
        """
        default_kernel = ""
        try:
            default_kernel = session.cmd_output("grubby --default-kernel")
        except Exception as e:
            test.log.warning("Save grub config failed: '%s'", e)

        return default_kernel

    def _restore_bootloader_config(session, default_kernel):
        error_context.context("Restore the grub to old version")

        if not default_kernel:
            test.log.warning("Could not get previous grub config, do noting.")
            return

        cmd = "grubby --set-default=%s" % default_kernel.strip()
        try:
            session.cmd(cmd)
        except Exception as e:
            test.error("Restore grub failed: '%s'" % e)

    def _clean_up_tmp_files(file_list):
        for f in file_list:
            try:
                os.unlink(f)
            except Exception as e:
                test.log.warning(
                    "Could remove tmp file '%s', error message: '%s'", f, e
                )

    def _build_params(param_str, default_value=""):
        param = _tmp_params_dict.get(param_str)
        if param:
            return {param_str: param}
        param = params.get(param_str)
        if param:
            return {param_str: param}
        return {param_str: default_value}

    error_context.context("Log into a guest")
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    timeout = float(params.get("login_timeout", 240))
    session = vm.wait_for_login(timeout=timeout)

    test.log.info("Guest kernel before install: %s", session.cmd("uname -a").strip())

    error_context.context("Save current default kernel information")
    default_kernel = _save_bootloader_config(session)

    # Check if there is local file in params, move local file to
    # client test (kernelinstall) directory.
    file_checklist = params.get("file_checklist", "")
    for i in file_checklist.split():
        var_list = map(_copy_file_to_test_dir, params.get(i, "").split())
        _tmp_params_dict[i] = " ".join(var_list)

    # Env preparation for test.
    install_type = params.get("install_type", "brew")
    sub_test_params = {}

    # rpm
    sub_test_params.update(_build_params("kernel_rpm_path"))
    sub_test_params.update(_build_params("kernel_deps_rpms"))

    # koji
    sub_test_params.update(_build_params("kernel_dep_pkgs"))
    sub_test_params.update(_build_params("kernel_sub_pkgs"))
    sub_test_params.update(_build_params("kernel_koji_tag"))
    sub_test_params.update(_build_params("need_reboot"))
    # git
    sub_test_params.update(_build_params("kernel_git_repo"))
    sub_test_params.update(_build_params("kernel_git_repo_base"))
    sub_test_params.update(_build_params("kernel_git_branch"))
    sub_test_params.update(_build_params("kernel_git_commit"))
    sub_test_params.update(_build_params("kernel_patch_list"))
    sub_test_params.update(_build_params("kernel_config"))
    sub_test_params.update(_build_params("kernel_config_list"))

    # src
    sub_test_params.update(_build_params("kernel_src_pkg"))
    sub_test_params.update(_build_params("kernel_config"))
    sub_test_params.update(_build_params("kernel_patch_list"))

    tag = params.get("kernel_tag")

    error_context.context("Generate control file for kernel install test")
    # Generate control file from parameters
    control_base = "params = %s\n"
    control_base += "job.run_test('kernelinstall'"
    control_base += ", install_type='%s'" % install_type
    control_base += ", params=params"
    if install_type == "tar" and tag:
        control_base += ", tag='%s'" % tag
    control_base += ")"
    control_dir = os.path.join(data_dir.get_root_dir(), "shared", "control")
    test_control_file = "kernel_install.control"
    test_control_path = os.path.join(control_dir, test_control_file)

    control_str = control_base % sub_test_params
    try:
        fd = open(test_control_path, "w")
        fd.write(control_str)
        fd.close()
        _tmp_file_list.append(os.path.abspath(test_control_path))
    except IOError as e:
        _clean_up_tmp_files(_tmp_file_list)
        test.error("Fail to Generate control file, error message:\n '%s'" % e)

    params["test_control_file_install"] = test_control_file

    error_context.context("Launch kernel installation test in guest")
    utils_test.run_virt_sub_test(
        test, params, env, sub_type="autotest_control", tag="install"
    )

    if params.get("need_reboot", "yes") == "yes":
        error_context.context("Reboot guest after kernel is installed")
        session.close()
        try:
            vm.reboot()
        except Exception:
            _clean_up_tmp_files(_tmp_file_list)
            test.fail("Could not login guest after install kernel")

    # Run Subtest in guest with new kernel
    if "sub_test" in params:
        error_context.context("Run sub test in guest with new kernel")
        sub_test = params.get("sub_test")
        tag = params.get("sub_test_tag", "run")
        try:
            utils_test.run_virt_sub_test(test, params, env, sub_type=sub_test, tag=tag)
        except Exception as e:
            test.log.error(
                "Fail to run sub_test '%s', error message: '%s'", sub_test, e
            )

    if params.get("restore_defaut_kernel", "no") == "yes":
        # Restore grub
        error_context.context("Restore grub and reboot guest")
        try:
            session = vm.wait_for_login(timeout=timeout)
            _restore_bootloader_config(session, default_kernel)
        except Exception as e:
            _clean_up_tmp_files(_tmp_file_list)
            session.close()
            test.fail("Fail to restore to default kernel, error message:\n '%s'" % e)
        vm.reboot()

    session = vm.wait_for_login(timeout=timeout)
    test.log.info("Guest kernel after install: %s", session.cmd("uname -a").strip())

    # Finally, let me clean up the tmp files.
    _clean_up_tmp_files(_tmp_file_list)
