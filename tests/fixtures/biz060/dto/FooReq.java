package kr.co.kfs.asseterp.biz.foo.dto;

import java.time.LocalDate;
import java.util.List;

public record FooReq(
        List<Long> ids,
        LocalDate checkIn,
        String checkInStr
) {}
