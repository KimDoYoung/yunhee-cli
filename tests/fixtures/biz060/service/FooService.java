package kr.co.kfs.asseterp.biz.foo.service;

import java.time.LocalDate;
import java.util.List;
import org.springframework.stereotype.Service;
import kr.co.kfs.asseterp.biz.foo.dto.FooReq;

@Service
public class FooService {

    public List<Object> search(Long personId, LocalDate baseDate) {
        Long compId = user.getCompanyId();
        checkMine(user, personId);
        return List.of();
    }

    public int updateTime(Long id, FooReq req) {
        Long compId = user.getCompanyId();
        return 1;
    }

    public int deleteList(List<Long> ids) {
        user.requireSysAdmin();
        return ids.size();
    }

    public int updateAppr(Long id, Long apprId) {
        // 아무 검사 없음
        return 1;
    }

    private void checkMine(Object user, Long personId) {
        if (user.getUserId().equals(personId)) {
            return;
        }
    }
}
