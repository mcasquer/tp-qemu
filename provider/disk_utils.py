"""
Disk utilities function for managing disks and filesystems in guest environments.

This module contains a function related to disk write command execution on
different OS types.
"""

from virttest import utils_disk
from virttest.utils_misc import get_linux_drive_path
from virttest.utils_windows.drive import get_disk_props_by_serial_number


def execute_io_test(
    test,
    params,
    vm,
    image,
    fstype,
    dst_dir=None,
    io_command=None,
    timeout=60,
):
    """
    Execute the dd write test on the disk image inside the guest.
    Note: The target disk image should be the uninitialized disk.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param vm: The VM object.
    :param image: The image name. e.g: stg0
    :param dst_dir: The destination directory for I/O write testing.
    :param io_options: The options for I/O command.
    :param timeout: The timeout for the I/O command.
    """

    if fstype not in ("ntfs", "xfs"):
        test.error("The fstype is not supported, only 'xfs' and 'ntfs' are")

    session = vm.wait_for_login()
    is_windows = params["os_type"] == "windows"
    image_params = params.object_params(image)
    image_size = image_params.get("image_size")

    disk = None
    try:
        if is_windows:
            # Configure the empty disk for windows guest
            disk = get_disk_props_by_serial_number(session, image, ["Index"])["Index"]
            utils_disk.update_windows_disk_attributes(session, disk)
            utils_disk.clean_partition_windows(session, disk)
            driver = utils_disk.configure_empty_windows_disk(
                session, disk, image_size, fstype=fstype
            )[0]

            # Create the related destination dir for testing
            if dst_dir:
                dst_dir = f"{driver}:\\{dst_dir}"
            else:
                dst_dir = f"{driver}:\\{image}"
            session.cmd(f"mkdir {dst_dir}")
        else:
            # Configure the empty disk for linux guest
            disk = get_linux_drive_path(session, image)
            partition_name = disk.split("/")[2]
            utils_disk.create_filesyetem_linux(session, partition_name, fstype=fstype)

            # Create the related destination dir for testing
            if not dst_dir:
                dst_dir = f"/var/tmp/{image}"
            session.cmd(f"mkdir -p {dst_dir}")

            utils_disk.mount(disk, dst_dir, fstype=fstype, session=session)

        # Start to run I/O command
        destination = f"{dst_dir}\\test.dat" if is_windows else f"{dst_dir}/test.img"
        if io_command:
            io_cmd = io_command % destination
            session.cmd(io_cmd, timeout)
        else:
            test.cancel("The I/O command has not been configured")

    finally:
        # We need to try to clean up and roll back the environment finally.
        try:
            if disk:
                if not is_windows:
                    utils_disk.is_mount(disk, dst_dir, fstype=fstype, session=session)
                    utils_disk.umount(disk, dst_dir, fstype=fstype, session=session)
                    session.cmd(f"rm -rf {dst_dir}")
                    # Send only the disk ID
                    disk_id = disk.split("/")[-1]
                    utils_disk.clean_partition(session, disk_id, params["os_type"])
                else:
                    session.cmd(f'"RD /S /Q "{dst_dir}"')
                    utils_disk.clean_partition(session, disk, params["os_type"])
        except Exception as e:
            test.log.warning(str(e))
