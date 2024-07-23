from virttest import error_context
from virttest import utils_package


@error_context.context_aware
def run(test, params, env):
    """
    vm_hugetlb_selftests test
    1) Download the current kernel source RPM
    2) Extract the RPM files
    3) Extract the linux package and compile the mm selftests
    4) Execute the higetlb kernel selftests
    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment
    """
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    session = vm.wait_for_login()
    kernel_path = params.get("kernel_path", "/home/kernel")
    vm_arch = params["vm_arch_name"]
    pkgs = params.objects("depends_pkgs")
    if not utils_package.package_install(pkgs, session):
        test.cancel("Install dependency packages failed")

    session.cmd("mkdir -p %s" % kernel_path)
    kernel_version = session.cmd_output("uname -r").split(vm_arch)[0]
    error_context.base_context("The kernel version: %s" % kernel_version, test.log.info)

    error_context.context("Download the kernel source RPM", test.log.debug)
    session.cmd("cd %s" % kernel_path)
    session.cmd("brew download-build --rpm kernel-%ssrc.rpm" % kernel_version, 180)

    error_context.context("Extract the RPM files", test.log.debug)
    session.cmd("rpm2cpio kernel-*.rpm | cpio -div")
    session.cmd("tar -xvf linux-*.tar.xz")
    session.cmd("cd linux-*/tools/testing/selftests/mm")

    error_context.base_context("Compile the mm selftests", test.log.info)
    s, o = session.cmd_status_output("make")
    if s != 0:
        test.fail("Error during mm selftests compilation: %s" % o)

    error_context.base_context("Execute the hugetlb selftests", test.log.info)
    s, o = session.cmd_status_output("sh run_vmtests.sh -t hugetlb")
    if s != 0:
        test.fail("Error during hugetlb selftests execution: %s" % o)

    error_context.context("The hugeltb tests results: %s" % o, test.log.debug)
