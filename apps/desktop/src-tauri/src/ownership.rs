//! Windows process ownership is isolated from the protocol controller.

use std::{io, process::Command};

#[cfg(windows)]
pub struct Ownership(std::os::windows::io::OwnedHandle);

#[cfg(windows)]
impl Ownership {
    pub fn new() -> io::Result<Self> {
        use std::os::windows::io::{FromRawHandle, OwnedHandle};
        use windows_sys::Win32::System::JobObjects::{
            CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject,
        };
        // SAFETY: unnamed job, no inherited handle; OwnedHandle closes it exactly once.
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if handle.is_null() {
            return Err(io::Error::last_os_error());
        }
        let owned = unsafe { OwnedHandle::from_raw_handle(handle) };
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        // SAFETY: valid job handle and correctly sized, initialized information struct.
        if unsafe {
            SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                (&limits as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                std::mem::size_of_val(&limits) as u32,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(owned))
    }

    pub fn attach(&self, child: &std::process::Child) -> io::Result<()> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::AssignProcessToJobObject;
        // SAFETY: both handles remain alive for the duration of this call.
        if unsafe { AssignProcessToJobObject(self.0.as_raw_handle(), child.as_raw_handle()) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }
}

#[cfg(not(windows))]
pub struct Ownership;

#[cfg(not(windows))]
impl Ownership {
    pub fn new() -> io::Result<Self> {
        Ok(Self)
    }
    pub fn attach(&self, _: &std::process::Child) -> io::Result<()> {
        Ok(())
    }
}

pub fn configure(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = command;
}
