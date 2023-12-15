from avocado.utils import process
from virttest import data_dir
from virttest import storage


def run(test, params, env):
    """
    QCOW2 image resize test
    1) Resize the qcow2 image
    :param test: QEMU test object
    :param params: Dictionary with the test parameters
    :param env: Dictionary with test environment
    """

    timeout = params.get_numeric("login_timeout", 240)
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()
    session = vm.wait_for_login(timeout=timeout)

    disk_partition = "/dev/sda2"
    if "ovmf" in params.get("id"):
        disk_partition = "/dev/sda3"
    
    data_image = params.get("images").split()[-1]
    data_image_params = params.object_params(data_image)
    data_image_filename = storage.get_image_filename(data_image_params,
                                                     data_dir.get_data_dir())

    test.log.debug("The data_image_filename: %s" % data_image_filename)

    must_packages = params.get("must_packages")
    image_format = params.get("image_format")
    image_name = params.get("image_name").split("/")[-1]
    image_path = "/home/%s.%s" % (image_name, image_format)
    process.system_output("cp -rf %s %s" % (data_image_filename, image_path))
    image_path_ori = image_path + ".ori"
    new_image_size_increase = params.get("new_image_size_increase", "+50G")
    
    for package in must_packages.split():
        is_pkg_installed = process.system_output("rpm -qa %s" % package)
        if is_pkg_installed is None:
            process.system_output("dnf install -y %s" % package)
    process.system_output("qemu-img resize %s %s" % (image_path,
                                                     new_image_size_increase))
    process.system_output("cp -rf %s %s" % (image_path, image_path_ori))
    process.system_output("virt-resize -expand %s %s %s" % (disk_partition,
                                                            image_path_ori,
                                                            image_path))
    process.system_output("virt-filesystems --long -h --all -a %s" % image_path)

    if "ovmf" in params.get("id"):
        session.cmd_output("lvextend -l +100%%FREE /dev/mapper/rhel-root %s" % disk_partition)
        session.cmd_output("xfs_growfs /dev/mapper/rhel-root")
    
    session.close()
